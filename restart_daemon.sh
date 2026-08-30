#!/usr/bin/env bash
# Restart tts_daemon.py — จำคำสั่ง launchctl ไม่ไหว
#
#   ./restart_daemon.sh              # restart ผ่าน launchd (kickstart -k) — รับโค้ด daemon ใหม่
#   ./restart_daemon.sh --reinstall  # copy plist repo -> ~/Library/LaunchAgents แล้ว unload/load
#                                    #   (ใช้เมื่อ plist เปลี่ยน เช่น WorkingDirectory / env / Nice)
#   ./restart_daemon.sh --manual     # ไม่ยุ่ง launchd — unload agent แล้วรัน foreground เห็น log สด
#   ./restart_daemon.sh --clear-cache# ล้าง TTS_CACHE_DIR ก่อน restart (ค่า default ~/.cache/qwen_tts)
#   ./restart_daemon.sh --verify     # หลัง restart ยิง request จริง 1 ครั้ง เช็คว่าเข้า fast path
#
# flag รวมกันได้ เช่น: ./restart_daemon.sh --reinstall --verify
#
# - daemon นี้รันเป็น launchd user agent (KeepAlive) — kill เฉย ๆ มันจะ respawn
#   ต้องสั่งผ่าน launchctl เท่านั้น
set -euo pipefail

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJ"

PY="$PROJ/.venv/bin/python"
LABEL="com.liino.qwen-tts-daemon"
PLIST_SRC="$PROJ/launchd/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
SOCK="${TTS_DAEMON_SOCK:-/tmp/qwen_tts_daemon.sock}"
CACHE_DIR="${TTS_CACHE_DIR:-$HOME/.cache/qwen_tts}"
TELEMETRY="${TTS_TELEMETRY_LOG:-$HOME/Library/Logs/qwen_tts_daemon.log}"
GUI_TARGET="gui/$(id -u)/$LABEL"

DO_REINSTALL=0
DO_MANUAL=0
DO_CLEAR_CACHE=0
DO_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --reinstall)    DO_REINSTALL=1 ;;
    --manual)       DO_MANUAL=1 ;;
    --clear-cache)  DO_CLEAR_CACHE=1 ;;
    --verify)       DO_VERIFY=1 ;;
    -h|--help)      awk 'NR>1 && !/^#/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; exit 0 ;;
    *)              echo "ERROR: unknown flag '$arg' (ดู --help)" >&2; exit 1 ;;
  esac
done

[ -x "$PY" ] || { echo "ERROR: ไม่พบ .venv — python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

# --- ล้าง cache (optional) ---
if [ "$DO_CLEAR_CACHE" -eq 1 ]; then
  echo ">> ล้าง cache: $CACHE_DIR" >&2
  rm -rf "$CACHE_DIR"
fi

wait_for_sock() {
  # รอ socket โผล่หลัง daemon start (model โหลด ~3-10s)
  local tries=40
  while [ "$tries" -gt 0 ]; do
    [ -S "$SOCK" ] && { echo ">> socket พร้อม: $SOCK" >&2; return 0; }
    sleep 0.5
    tries=$((tries - 1))
  done
  echo "WARN: รอ $SOCK ไม่ขึ้นภายใน 20s — เช็ค log: tail -n40 $TELEMETRY" >&2
  return 1
}

if [ "$DO_MANUAL" -eq 1 ]; then
  # --- โหมด manual: กัน launchd แย่ง socket แล้วรัน foreground ---
  echo ">> unload launchd agent (ถ้ามี)" >&2
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
    || launchctl unload "$PLIST_DST" 2>/dev/null \
    || true
  pkill -f 'tts_daemon\.py' 2>/dev/null || true
  sleep 1
  echo ">> รัน foreground — Ctrl-C เพื่อหยุด (load agent กลับด้วย: launchctl load $PLIST_DST)" >&2
  exec "$PY" tts_daemon.py

elif [ "$DO_REINSTALL" -eq 1 ]; then
  # --- reinstall plist จาก repo ---
  [ -f "$PLIST_SRC" ] || { echo "ERROR: ไม่พบ $PLIST_SRC" >&2; exit 1; }
  echo ">> copy plist: $PLIST_SRC -> $PLIST_DST" >&2
  mkdir -p "$(dirname "$PLIST_DST")"
  cp "$PLIST_SRC" "$PLIST_DST"
  echo ">> unload + load" >&2
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  launchctl load "$PLIST_DST"
  wait_for_sock || true

else
  # --- restart ปกติผ่าน launchd ---
  if launchctl print "$GUI_TARGET" >/dev/null 2>&1; then
    echo ">> kickstart -k $GUI_TARGET" >&2
    launchctl kickstart -k "$GUI_TARGET"
  elif [ -f "$PLIST_DST" ]; then
    echo ">> agent ยังไม่ load — load $PLIST_DST" >&2
    launchctl load "$PLIST_DST"
  else
    echo "ERROR: ยังไม่ได้ติดตั้ง agent — รันด้วย --reinstall ก่อน" >&2
    exit 1
  fi
  wait_for_sock || true
fi

# --- สรุปสถานะ ---
echo ">> launchctl list:" >&2
launchctl list | grep -E "PID|$LABEL" || echo "   (ไม่พบ $LABEL ใน list)" >&2

# --- verify (optional): ยิง request จริงผ่าน fast path ---
if [ "$DO_VERIFY" -eq 1 ]; then
  OUT="$PROJ/outputs/restart_check.wav"
  mkdir -p "$PROJ/outputs"
  echo ">> verify: ยิง request ผ่าน qwen_clone_tts.py" >&2
  ERR="$("$PY" qwen_clone_tts.py --text "ทดสอบ restart daemon" --mood gentle --out "$OUT" 2>&1 1>/dev/null || true)"
  echo "$ERR" >&2
  if printf '%s' "$ERR" | grep -q "via daemon"; then
    echo ">> OK — เข้า daemon fast path ($OUT)" >&2
  else
    echo "WARN: ไม่เห็น 'via daemon' — อาจ fallback in-process หรือ daemon ยังไม่พร้อม" >&2
    exit 1
  fi
fi
