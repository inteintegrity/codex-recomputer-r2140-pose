#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -f app.pid ]; then
  pid="$(cat app.pid)"
  if kill -0 "$pid" 2>/dev/null && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q 'python -u app.py'; then
    kill "$pid"
    rm app.pid
    echo "Pose Studio stopped."
  fi
fi
