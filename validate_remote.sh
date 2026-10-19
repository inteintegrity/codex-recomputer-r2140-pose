set -eu
cd "$(dirname "$0")"
.venv/bin/python - <<'PY'
import requests,time,json,subprocess,os
from pathlib import Path
s=requests.Session(); s.trust_env=False
base='http://127.0.0.1:'+os.environ.get('PORT','8080')
Path('data').mkdir(exist_ok=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i','video/test.mp4','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','2','-c:v','copy','-c:a','aac','data/audio-check.mp4'],check=True)
headers={'X-Pose-Upload':'1','X-Filename':'audio-check.mp4','Content-Type':'video/mp4'}
def wait(jid):
    for _ in range(60):
        j=s.get(base+'/api/jobs/'+jid).json()
        if j['status'] in ('completed','failed'): return j
        time.sleep(.5)
    raise TimeoutError('Job did not finish')
r=s.post(base+'/api/jobs',data=b'not a video',headers={**headers,'X-Filename':'invalid.txt'})
assert r.status_code==400, r.text
r=s.post(base+'/api/jobs',data=b'not a video',headers={**headers,'X-Filename':'invalid.mp4'})
assert r.status_code==202, r.text
bad=wait(r.json()['id']);assert bad['status']=='failed',bad
assert not s.get(base+'/api/health').json()['busy']
with open('data/audio-check.mp4','rb') as f:r=s.post(base+'/api/jobs',data=f,headers=headers)
assert r.status_code==202,r.text
jid=r.json()['id']
with open('data/audio-check.mp4','rb') as f:busy=s.post(base+'/api/jobs',data=f,headers=headers)
assert busy.status_code==409,busy.text
j=wait(jid);assert j['status']=='completed',j
assert j['frames']>=50 and j['inference_fps']>0 and j['visible_keypoints']>0,j
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name,nb_frames','-of','json','data/'+jid+'/output.mp4']))
video=next(x for x in probe['streams'] if x['codec_type']=='video')
assert int(video['nb_frames'])==j['frames'],probe
assert any(x['codec_type']=='audio' and x['codec_name']=='aac' for x in probe['streams']),probe
range_request=s.get(base+'/api/jobs/'+jid+'/video',headers={'Range':'bytes=0-31'})
assert range_request.status_code==206
assert s.get(base+'/api/jobs/'+jid+'/video?download=1').headers['Content-Disposition'].startswith('attachment')
assert not s.get(base+'/api/health').json()['busy']
Path('validation.json').write_text(json.dumps({'invalid_extension':'passed','invalid_video_recovery':'passed','busy_guard':'passed','repeat_inference':'passed','video_seeking':'passed','download':'passed','audio_job':j,'output_streams':probe},indent=2))
print(json.dumps(j,indent=2))
PY
