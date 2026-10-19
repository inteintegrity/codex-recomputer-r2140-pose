#!/bin/sh
set -eu
cd "$(dirname "$0")"
for tool in python3 ffmpeg ffprobe hailortcli; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool. No system changes were made." >&2; exit 1; }
done
python3 - <<'PY'
import cv2, numpy, PIL, hailo_platform
if hailo_platform.__version__ != '4.23.0':
    raise SystemExit('This release was verified with HailoRT 4.23.0. Keep the existing driver and verify compatibility before continuing.')
print('Reusing system HailoRT', hailo_platform.__version__, 'OpenCV', cv2.__version__, 'NumPy', numpy.__version__)
PY
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python download_model.py
echo "Setup complete. Run: sh start.sh"
