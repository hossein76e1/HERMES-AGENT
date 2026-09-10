#!/usr/bin/env bash
# نگهبان هواشناسی ایران: سرور FastAPI و تانل Cloudflare را زنده نگه می‌دارد
# هر ۳۰ ثانیه چک می‌کند؛ اگر افتاده باشند دوباره راه می‌اندازد و لینک جدید را ثبت می‌کند.
set -u
PORT=8734
URL_FILE=/data/workspace/iran-weather/tunnel_url.txt
LOG=/data/workspace/iran-weather/watchdog.log
CFLOG=/tmp/cloudflared.log
mkdir -p "$(dirname "$URL_FILE")"

start_server() {
  if ! curl -s --max-time 4 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    cd /data/workspace/iran-weather
    nohup /usr/local/bin/python3 -m uvicorn app.server:app --host 127.0.0.1 --port "$PORT" --log-level warning >> "$LOG" 2>&1 &
    echo "$(date '+%Y-%m-%d %H:%M') server restarted pid $!" >> "$LOG"
    sleep 3
  fi
}

start_tunnel() {
  local oldurl newurl
  oldurl="$(cat "$URL_FILE" 2>/dev/null || true)"
  if [ -n "$oldurl" ] && curl -s --max-time 4 "$oldurl/api/health" >/dev/null 2>&1; then
    return 0
  fi
  pkill -f 'cloudflared tunnel' 2>/dev/null
  sleep 1
  ( /usr/local/bin/cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$CFLOG" 2>&1 & )
  for i in $(seq 1 25); do
    newurl="$(grep -aoE 'https://[a-z0-9.-]+\.trycloudflare\.com' "$CFLOG" | head -1)"
    if [ -n "$newurl" ]; then
      echo "$newurl" > "$URL_FILE"
      echo "$(date '+%Y-%m-%d %H:%M') tunnel up: $newurl" >> "$LOG"
      return 0
    fi
    sleep 1
  done
  echo "$(date '+%Y-%m-%d %H:%M') WARN: tunnel did not come up" >> "$LOG"
}

while true; do
  start_server
  start_tunnel
  sleep 30
done
