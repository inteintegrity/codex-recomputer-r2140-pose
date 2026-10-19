"""LAN video pose workspace. Inference/decoder reused from hailo-ai/hailo-apps."""
import json
import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.parse import unquote
import uuid

import cv2
import numpy as np
from flask import Flask, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from official_inference import HailoInfer
from official_pose_utils import PoseEstPostProcessing, JOINT_PAIRS

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
MODEL = ROOT / 'models/yolov8m_pose.hef'
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 1024**3
gate = threading.Lock()
state_lock = threading.RLock()
jobs = {}
for path in DATA.glob('*/job.json'):
    try:
        j = json.loads(path.read_text())
        if j['status'] not in ('completed', 'failed'):
            j.update(status='failed', error='Processing was interrupted. Please upload again.')
        jobs[j['id']] = j
    except (ValueError, KeyError):
        pass


def update(j, **values):
    with state_lock:
        j.update(values)
        target = DATA / j['id'] / 'job.json'
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps(j))
        tmp.replace(target)


def draw(frame, results, post, conf, joint_conf):
    h, w = frame.shape[:2]
    people = 0
    visible = 0
    for box, score, points, scores in zip(results['bboxes'][0], results['scores'][0], results['keypoints'][0], results['joint_scores'][0]):
        score = float(score[0])
        if score < conf:
            continue
        people += 1
        x1,y1,x2,y2 = post.map_box_to_original_coords(box.copy(), w,h,640,640)
        points = post.map_keypoints_to_original_coords(points.copy(),w,h,640,640)
        valid = scores[:,0] >= joint_conf
        visible += int(valid.sum())
        cv2.rectangle(frame,(x1,y1),(x2,y2),(90,235,168),2)
        label = f'PERSON {score:.0%}'
        cv2.rectangle(frame,(x1,max(0,y1-25)),(min(w,x1+135),y1),(90,235,168),-1)
        cv2.putText(frame,label,(x1+4,max(15,y1-7)),cv2.FONT_HERSHEY_SIMPLEX,.48,(25,40,30),1,cv2.LINE_AA)
        for a,b in JOINT_PAIRS:
            if valid[a] and valid[b]:
                cv2.line(frame,tuple(points[a].astype(int)),tuple(points[b].astype(int)),(255,190,95),3,cv2.LINE_AA)
        for p,v in zip(points,valid):
            if v:
                xy=tuple(p.astype(int))
                cv2.circle(frame,xy,4,(25,30,35),-1,cv2.LINE_AA)
                cv2.circle(frame,xy,3,(120,245,255),-1,cv2.LINE_AA)
    return people, visible


def process(j):
    folder = DATA / j['id']
    cap = None
    engine = None
    encoder = None
    log = None
    started = time.perf_counter()
    try:
        update(j,status='loading',message='Opening video and configuring Hailo-8')
        cap = cv2.VideoCapture(str(folder/'input.mp4'))
        if not cap.isOpened():
            raise ValueError('This file is not a decodable MP4 video.')
        w,h = int(cap.get(3)),int(cap.get(4))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not (0<w<=4096 and 0<h<=2160 and math.isfinite(fps) and 0<fps<=240 and 0<total<=216000):
            raise ValueError('Unsupported video. Use a valid MP4 up to 4096 x 2160 and 216,000 frames.')
        # Estimate output space before encoding (up to 16 Mbit/s plus 512 MiB reserve).
        if shutil.disk_usage(DATA).free < total/fps*2_000_000 + 512*1024**2:
            raise ValueError('Insufficient storage for this video. Try a shorter clip.')
        update(j,width=w,height=h,source_fps=round(fps,3),total_frames=total,duration=round(total/fps,2))
        engine = HailoInfer(str(MODEL),1,input_type='UINT8',output_type='FLOAT32')
        post = PoseEstPostProcessing(100,j['confidence'],.65,15,[8,16,32])
        log = (folder/'encoder.log').open('wb')
        encoder = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','23','-pix_fmt','yuv420p',str(folder/'silent.mp4')],stdin=subprocess.PIPE,stderr=log)
        n=0; infer_seconds=0.; people_total=0; joint_total=0
        peak=0; sample_at=0
        stage_start=time.perf_counter()
        while True:
            ok, frame=cap.read()
            if not ok:
                break
            scale=min(640/w,640/h)
            nw,nh=int(w*scale),int(h*scale)
            image=np.full((640,640,3),114,np.uint8)
            x,y=(640-nw)//2,(640-nh)//2
            image[y:y+nh,x:x+nw]=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),(nw,nh))
            done=threading.Event(); result={}
            def callback(completion_info,bindings_list):
                try:
                    if completion_info.exception:
                        result['error']=str(completion_info.exception)
                    else:
                        result['raw']={name: np.expand_dims(bindings_list[0].output(name).get_buffer().copy(),0) for name in engine.output_type}
                except Exception as e:
                    result['error']=str(e)
                finally:
                    done.set()
            tick=time.perf_counter()
            job=engine.run([image],callback)
            job.wait(15000)
            if not done.wait(15):
                raise TimeoutError('Hailo-8 inference timed out.')
            infer_seconds += time.perf_counter()-tick
            if 'error' in result:
                raise RuntimeError(result['error'])
            decoded=post.post_process(result['raw'],640,640,1)
            people,joints=draw(frame,decoded,post,j['confidence'],j['joint_confidence'])
            n+=1; people_total+=people; joint_total+=joints
            inference_fps=n/infer_seconds
            pipeline_fps=n/(time.perf_counter()-stage_start)
            cv2.rectangle(frame,(10,10),(min(w-1,490),65),(24,30,37),-1)
            cv2.putText(frame,f'HAILO-8 | INFERENCE {inference_fps:.1f} FPS',(20,34),cv2.FONT_HERSHEY_SIMPLEX,.55,(100,240,190),1,cv2.LINE_AA)
            cv2.putText(frame,f'YOLOv8m Pose | People: {people} | Frame {n}',(20,55),cv2.FONT_HERSHEY_SIMPLEX,.45,(240,240,240),1,cv2.LINE_AA)
            encoder.stdin.write(frame.tobytes())
            if people>peak or n==1:
                peak=people
                cv2.imwrite(str(folder/'preview.jpg'),frame)
                sample_at=n
            if n%5==0 or n==1:
                update(j,status='processing',message='Estimating poses on Hailo-8',frames=n,progress=min(98,round(n/total*98,1)),inference_fps=round(inference_fps,2),pipeline_fps=round(pipeline_fps,2),people=people,person_detections=people_total,visible_keypoints=joint_total,elapsed=round(time.perf_counter()-started,1))
        if n==0:
            raise ValueError('The MP4 does not contain readable video frames.')
        if n < total-2:
            raise ValueError(f'Video decoding stopped early at frame {n} of {total}. The file may be damaged.')
        encoder.stdin.close()
        if encoder.wait(timeout=120):
            raise RuntimeError('Video encoding failed. See encoder.log.')
        update(j,status='finalizing',progress=99,message='Preparing browser video and preserving audio',frames=n)
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(folder/'silent.mp4'),'-i',str(folder/'input.mp4'),'-map','0:v:0','-map','1:a:0?','-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',str(folder/'output.mp4')],check=True,timeout=180,stderr=log)
        (folder/'silent.mp4').unlink()
        update(j,status='completed',progress=100,message='Your pose video is ready',frames=n,inference_fps=round(n/infer_seconds,2),pipeline_fps=round(n/(time.perf_counter()-stage_start),2),inference_seconds=round(infer_seconds,3),elapsed=round(time.perf_counter()-started,2),person_detections=people_total,visible_keypoints=joint_total,peak_people=peak,preview_frame=sample_at,output_bytes=(folder/'output.mp4').stat().st_size)
    except Exception as e:
        logging.exception('Job %s failed',j['id'])
        update(j,status='failed',message='Processing failed',error=str(e))
    finally:
        if cap is not None: cap.release()
        if encoder is not None and encoder.poll() is None:
            encoder.kill(); encoder.wait()
        if engine is not None:
            try:
                engine.close()
                engine.target.release()
            except Exception: logging.exception('Hailo cleanup')
        if log: log.close()
        gate.release()


@app.get('/')
def index():
    return send_file(ROOT/'static/index.html')


@app.get('/api/health')
def health():
    import hailo_platform
    return jsonify(status='ready',device='Hailo-8',model='YOLOv8m-Pose',hailort=hailo_platform.__version__,model_ready=MODEL.exists(),busy=gate.locked(),free_gb=round(shutil.disk_usage(DATA).free/1024**3,2))


@app.get('/api/jobs')
def list_jobs():
    with state_lock:
        return jsonify(sorted(jobs.values(),key=lambda j:j['created'],reverse=True)[:30])


@app.post('/api/jobs')
def upload():
    # Prevent cross-origin browser form uploads; this LAN app has no public account system.
    if request.headers.get('X-Pose-Upload') != '1': abort(400,description='Missing upload header.')
    filename=unquote(request.headers.get('X-Filename','video.mp4'))
    if not filename.lower().endswith('.mp4'): abort(400,description='Please select an MP4 video.')
    if request.content_length is None or request.content_length<=0: abort(400,description='The file is empty or its size is unknown.')
    try:
        conf=float(request.args.get('confidence',.5)); joint=float(request.args.get('joint_confidence',.5))
        if not (.1<=conf<=.95 and .1<=joint<=.95): raise ValueError()
    except ValueError: abort(400,description='Confidence must be between 0.1 and 0.95.')
    if not MODEL.exists(): abort(503,description='The pose model is unavailable.')
    if shutil.disk_usage(DATA).free < request.content_length*2+512*1024**2: abort(507,description='Not enough storage. Delete an older job or upload a smaller video.')
    if not gate.acquire(blocking=False): abort(409,description='The accelerator is busy. Wait for the current job to finish.')
    folder=None
    try:
        jid=uuid.uuid4().hex
        folder=DATA/jid; folder.mkdir()
        with (folder/'input.mp4').open('wb') as f:
            shutil.copyfileobj(request.stream,f,1024*1024)
        j=dict(id=jid,filename=filename[:240],created=time.time(),status='queued',message='Waiting for Hailo-8',progress=0,frames=0,inference_fps=0,pipeline_fps=0,confidence=conf,joint_confidence=joint)
        update(j)
        with state_lock: jobs[jid]=j
        threading.Thread(target=process,args=(j,),daemon=True).start()
        return jsonify(j),202
    except Exception:
        if folder: shutil.rmtree(folder)
        gate.release()
        raise


def get_job(jid):
    with state_lock:
        if jid not in jobs: abort(404)
        return jobs[jid]


@app.get('/api/jobs/<jid>')
def status(jid):
    with state_lock: return jsonify(get_job(jid))


@app.get('/api/jobs/<jid>/<asset>')
def asset(jid,asset):
    j=get_job(jid)
    names={'video':'output.mp4','preview':'preview.jpg','original':'input.mp4','report':'job.json'}
    if asset not in names: abort(404)
    if asset=='video' and j['status']!='completed': abort(409)
    path=DATA/jid/names[asset]
    if not path.is_file(): abort(404)
    return send_file(path,conditional=True,as_attachment=request.args.get('download')=='1',download_name='pose-'+Path(j['filename']).stem+'.mp4' if asset=='video' else path.name)


@app.delete('/api/jobs/<jid>')
def delete(jid):
    with state_lock:
        j=get_job(jid)
        if j['status'] not in ('completed','failed'): abort(409,description='Wait for processing to finish before deleting.')
        shutil.rmtree(DATA/jid)
        del jobs[jid]
    return '',204


@app.errorhandler(HTTPException)
def http_error(e): return jsonify(error=e.description),e.code


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='SAMEORIGIN'
    if request.path.startswith('/api/') and '/video' not in request.path and '/original' not in request.path:
        response.headers['Cache-Control']='no-store'
    return response


if __name__=='__main__':
    from waitress import serve
    logging.basicConfig(level=logging.INFO)
    serve(app,host='0.0.0.0',port=int(os.environ.get('PORT','8080')),threads=6,max_request_body_size=1024**3,channel_timeout=300)
