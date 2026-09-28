#!/bin/zsh
set -euo pipefail

SITE_ROOT="${SITE_ROOT:-/Users/zhushihao/Services/verifin-site}"
VERIFIN_ROOT="${VERIFIN_ROOT:-/Users/zhushihao/Services/verifin}"
PYTHON="${PYTHON:-$VERIFIN_ROOT/.venv/bin/python}"
PID_FILE="${PID_FILE:-/Users/zhushihao/Services/verifin.pid}"
LOG_FILE="${LOG_FILE:-/Users/zhushihao/Services/logs/verifin.log}"

cd "$SITE_ROOT"
git pull --ff-only

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(<"$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid"
    for _ in {1..20}; do
      kill -0 "$old_pid" 2>/dev/null || break
      sleep 0.25
    done
  fi
fi

mkdir -p "${LOG_FILE:h}"
VERIFIN_ROOT="$VERIFIN_ROOT" nohup "$PYTHON" -m uvicorn server:app \
  --host 0.0.0.0 --port 8951 >"$LOG_FILE" 2>&1 </dev/null &
echo $! >"$PID_FILE"

for _ in {1..30}; do
  if curl --noproxy '*' -fsS http://127.0.0.1:8951/api/health >/dev/null; then
    echo "VeriFin updated and running on port 8951."
    exit 0
  fi
  sleep 1
done

echo "VeriFin failed to become healthy. Recent log:" >&2
tail -n 80 "$LOG_FILE" >&2
exit 1
