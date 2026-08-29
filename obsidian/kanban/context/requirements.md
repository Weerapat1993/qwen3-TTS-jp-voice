# Project Requirements: Qwen3-TTS Apple Silicon

## Product-Level Source Of Truth

โปรเจกต์นี้ไม่มี `prd.md` กลาง ใช้ไฟล์เหล่านี้เป็นแหล่งอ้างอิงภาพรวมแทน:

- `README.md` (root) — overview, CLI reference, daemon protocol/config, troubleshooting, requirements
- `README_HERMES.md` (root) — Hermes CLI / MCP bridge integration notes (แยกจาก TTS core flow)
- ไม่มี `AGENTS.md` ในโปรเจกต์นี้ — ถ้า ticket ต้องการ convention เชิงสถาปัตยกรรม ให้ยึด README.md และโค้ดจริงแทน

Agent AI ควรอ่าน `README.md` ก่อนทำงานเหล่านี้:

- เพิ่ม/แก้ CLI flag ใน `qwen_clone_tts.py` หรือ `main.py`
- แก้ daemon protocol, queue, cache key, หรือ env var ใน `tts_daemon.py`
- เพิ่ม script entry point ใหม่ที่ผู้ใช้ต้องเรียกตรง (เช่น `tune_voice.py`)
- เปลี่ยนพฤติกรรมที่กระทบ backward compatibility ของ client (`qwen_clone_tts.py`) กับ daemon

ถ้า requirement ใหม่ขัดกับพฤติกรรมเดิมใน README.md ให้แจ้ง conflict และถามผู้ใช้ว่าจะปรับ README/behavior หรือถือเป็น exception เฉพาะงานนั้น

## Goal

CLI + background daemon สำหรับ voice cloning / text-to-speech (ไทย/ญี่ปุ่น/อังกฤษ) บน Apple Silicon (M1–M4) โดยใช้ Qwen3-TTS ผ่าน MLX/mlx-audio รันแบบ local ล้วน ไม่มี web server, ไม่มี database, ไม่มี Discord bot

## Tech Stack

- Python 3.10+, macOS Apple Silicon เท่านั้น (ต้องมี Metal/MLX)
- `mlx`, `mlx-audio` (git dependency), `mlx-lm` — model inference
- `ffmpeg` (external binary, ไม่ใช่ pip package) — แปลง MP3 และต่อไฟล์เสียงยาว
- `librosa`, `soundfile`, `soxr`, `pyloudnorm` — audio processing/loudness
- `typer-slim` (มีใน requirements.txt) และ stdlib `argparse` — CLI ของแต่ละ script ใช้ `argparse` ตรง ๆ ไม่ใช่ typer app
- stdlib `socket` + line-delimited JSON — daemon protocol (`tts_daemon.py`)
- `launchd` plist (`launchd/com.liino.qwen-tts-daemon.plist`) — ติดตั้งเป็น background service (ผู้ใช้ต้อง `launchctl load` เอง)
- ไม่มี ORM/DB, ไม่มี web framework, ไม่มี test framework ติดตั้งอยู่ในโปรเจกต์นี้ (ไม่มี `pytest`, ไม่มี `pyproject.toml`, ไม่มี `tests/`)

## Functional Requirements

- Voice cloning จาก `voices/<name>.wav` (+ `voices/<name>.txt` เป็น reference transcript แบบ optional)
- Custom voice / voice design ผ่าน `--instruct` และ mood preset (`MOOD_PRESETS` ใน `qwen_clone_tts.py`)
- Interactive menu (`main.py`) และ non-interactive scripting CLI (`qwen_clone_tts.py`) ที่ report ผลผ่าน stdout/stderr + exit code (`OK <path>` / `ERROR: ...`)
- จำกัดข้อความไม่เกิน 300 ตัวอักษร (`MAX_CHARS`); โหมด `--stdin` อ่านจากไฟล์ แบ่ง chunk เองแล้วต่อเสียงเป็นไฟล์เดียว (ใช้เสียง Liino คงที่)
- แปลงเป็น MP3 ผ่าน ffmpeg ด้วย `--mp3`
- Background daemon (`tts_daemon.py`): โหลดโมเดลครั้งเดียว, FIFO queue, queue timeout, cache ตาม `(voice, text, instruct)`, idle unload, telemetry เป็น JSONL
- `qwen_clone_tts.py` ต้องตรวจจับ daemon อัตโนมัติและ fallback เป็นโหลดโมเดลเองถ้า daemon ไม่ทำงาน (ห้ามลบ fallback path นี้)
- Voice tuning helper (`tune_voice.py`)

## Backend / Script Requirements

- Entry point อยู่ที่ root ของ repo ตรง ๆ ไม่มี `src/` package layout: `main.py`, `qwen_clone_tts.py`, `tts_daemon.py`, `tune_voice.py`
- โมเดลอยู่ที่ `models/<model-dir>` (ไม่ commit เข้า git — ดาวน์โหลดจาก HuggingFace เอง); default `models/Qwen3-TTS-12Hz-1.7B-Base-8bit`
- เสียงต้นแบบอยู่ที่ `voices/<name>.wav` (+ optional `.txt`); character preset อยู่ที่ `characters/`
- ไฟล์เสียงที่ generate แล้วอยู่ที่ `outputs/`; ของเก่า/สำรองอยู่ที่ `backups/`
- Config ของ daemon ทั้งหมดมาจาก environment variable เท่านั้น ไม่มี config file: `TTS_DAEMON_SOCK`, `TTS_CACHE_DIR`, `TTS_QUEUE_TIMEOUT`, `TTS_TELEMETRY_LOG`, `TTS_IDLE_UNLOAD`
- Daemon protocol: ส่ง JSON object เดียว + `\n` เป็น request, รับ JSON object เดียว + `\n` เป็น response ผ่าน Unix domain socket — เปลี่ยน schema ต้องคง backward compatible กับ `qwen_clone_tts.py` client เดิม
- `launchd/com.liino.qwen-tts-daemon.plist` เป็น template — แก้ path แล้วต้อง reinstall เอง (`launchctl load`) ไม่มี automation ให้
- Priority ของ daemon ทำผ่าน macOS Process QoS (`taskpolicy`) แบบ best-effort เท่านั้น ไม่ใช่ `nice` เชิงลบ (ต้อง root)

## Coding Conventions (รายละเอียดเพิ่มเติมดู `coding-style.md`)

- ไม่มี lint/format config ใน repo (ไม่มี ruff/black/pyproject.toml) — ยึดสไตล์เดิมของไฟล์ที่แก้เป็นหลัก
- ไม่มี test suite ในโปรเจกต์นี้ตอนนี้ — validate ด้วยการรัน CLI/daemon จริงแทน
- Report ผลลัพธ์ CLI ผ่าน stdout/stderr text + exit code ตาม convention เดิม ไม่ใช้ `logging` module สำหรับ user-facing output (daemon telemetry ใช้ raw JSONL แยกต่างหาก)
