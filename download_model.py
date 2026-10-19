"""Download the official precompiled Hailo-8 pose model; never convert/train."""
import hashlib
from pathlib import Path
import urllib.request

URL = 'https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.18.0/hailo8/yolov8m_pose.hef'
SHA256 = '54f22e23ee5e161e3b5d8507add82035122f72fa6357b453eb8773c63c0eb4b7'
MODEL = Path(__file__).resolve().parent / 'models/yolov8m_pose.hef'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    MODEL.parent.mkdir(exist_ok=True)
    if MODEL.exists() and digest(MODEL) == SHA256:
        print(f'Already verified: {MODEL}')
        return
    tmp = MODEL.with_suffix('.hef.part')
    print(f'Downloading official precompiled model from {URL}')
    try:
        with urllib.request.urlopen(URL, timeout=120) as response, tmp.open('wb') as f:
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
        if digest(tmp) != SHA256:
            raise RuntimeError('Model SHA-256 mismatch; refusing the download.')
        tmp.replace(MODEL)
    finally:
        tmp.unlink(missing_ok=True)
    print(f'Verified Hailo-8 model: {MODEL}')


if __name__ == '__main__':
    main()
