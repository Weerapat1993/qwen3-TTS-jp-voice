#!/usr/bin/env bash
# รัน Discord say bot (discord_say_bot.py) แบบจำคำสั่งไม่ไหว
#
#   ./run_say_bot.sh            # รัน foreground เห็น log สด
#   ./run_say_bot.sh --bg       # รัน background, log ไป /tmp/say_bot.log
#
# - โหลด DISCORD_BOT_TOKEN จาก .env (ไฟล์นี้ไม่ auto-load ในโค้ด — ดู README.md)
# - kill process บอทเก่าที่ค้างก่อนเสมอ (double process = เสียงเล่นซ้อน/loop)
# - เตือนถ้า tts_daemon.py ยังไม่รัน (บอทไม่ fallback โหลดโมเดลเอง)
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJ"

PY="$PROJ/.venv/bin/python"
SOCK="/tmp/qwen_tts_daemon.sock"
LOG="/tmp/say_bot.log"

[ -x "$PY" ] || { echo "ERROR: ไม่พบ .venv — python3 -m venv .venv && pip install -r requirements.txt" >&2; exit 1; }

# --- token จาก .env (เอาเฉพาะ DISCORD_BOT_TOKEN ไม่ยุ่งกับ NOTION_API_TOKEN) ---
if [ -z "${DISCORD_BOT_TOKEN:-}" ]; then
  [ -f "$PROJ/.env" ] || { echo "ERROR: ไม่มี .env และ DISCORD_BOT_TOKEN ไม่ได้ export ไว้" >&2; exit 1; }
  DISCORD_BOT_TOKEN="$(grep -E '^DISCORD_BOT_TOKEN=' "$PROJ/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  export DISCORD_BOT_TOKEN
fi
[ -n "${DISCORD_BOT_TOKEN:-}" ] || { echo "ERROR: DISCORD_BOT_TOKEN ว่าง — เช็ค .env" >&2; exit 1; }

# --- kill บอทเก่าที่ค้าง ---
OLD="$(pgrep -f 'discord_say_bot\.py' || true)"
if [ -n "$OLD" ]; then
  echo "kill บอทเก่า: $OLD" >&2
  # shellcheck disable=SC2086
  kill $OLD 2>/dev/null || true
  sleep 1
fi

# --- เตือนถ้า daemon ไม่รัน ---
[ -S "$SOCK" ] || echo "WARN: ไม่พบ $SOCK — start ก่อน: $PY tts_daemon.py &" >&2

if [ "${1:-}" = "--bg" ]; then
  nohup "$PY" discord_say_bot.py > "$LOG" 2>&1 &
  echo "บอทรัน background (PID $!) — log: tail -f $LOG" >&2
else
  exec "$PY" discord_say_bot.py
fi
