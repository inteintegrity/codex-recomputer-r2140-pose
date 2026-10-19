#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -f app.pid ] && kill -0 "$(cat app.pid)" 2>/dev/null; then
  echo "Pose Studio is already running (PID $(cat app.pid))."
  exit 0
fi
nohup .venv/bin/python -u app.py >>app.log 2>&1 </dev/null &
echo $! >app.pid
echo "Pose Studio started on port ${PORT:-8080}. Open http://<board-ip>:${PORT:-8080}"
