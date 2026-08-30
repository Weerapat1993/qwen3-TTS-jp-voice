# Project Requirements: Qwen3-TTS Apple Silicon

## Product-Level Source Of Truth

โปรเจกต์นี้ไม่มี `prd.md` กลาง ใช้ไฟล์เหล่านี้เป็นแหล่งอ้างอิงภาพรวมแทน:

- `README.md` (root) — overview, CLI reference, daemon protocol/config, Discord bot, `/transcribe`, troubleshooting, requirements
- `README_HERMES.md` (root) — Hermes agent integration notes: external consumer ที่ shell out `qwen_clone_tts.py --stdin` เป็น TTS provider (แยกจาก TTS core flow)
- ไม่มี `AGENTS.md` ในโปรเจกต์นี้ — ถ้า ticket ต้องการ convention เชิงสถาปัตยกรรม ให้ยึด README.md และโค้ดจริงแทน

Agent AI ควรอ่าน `README.md` ก่อนทำงานเหล่านี้:

- เพิ่ม/แก้ CLI flag ใน `qwen_clone_tts.py` หรือ `main.py`
- แก้ daemon protocol, queue, cache key, หรือ env var ใน `tts_daemon.py`
- เพิ่ม/เปลี่ยน Discord slash command surface ใน `discord_say_bot.py` (`/say`, `/transcribe`)
- เพิ่ม/เปลี่ยน mood preset (`MOOD_PRESETS`) หรือ emoji↔mood map (`say_moods.py`, `transcribe_mood.py`)
- เพิ่ม script entry point ใหม่ที่ผู้ใช้ต้องเรียกตรง (เช่น `tune_voice.py`)
- เปลี่ยนพฤติกรรมที่กระทบ backward compatibility ของ client (`qwen_clone_tts.py`) กับ daemon

ถ้า requirement ใหม่ขัดกับพฤติกรรมเดิมใน README.md ให้แจ้ง conflict และถามผู้ใช้ว่าจะปรับ README/behavior หรือถือเป็น exception เฉพาะงานนั้น

## Goal

CLI + background daemon + Discord bot สำหรับ voice cloning / text-to-speech (ไทย/ญี่ปุ่น/อังกฤษ) บน Apple Silicon (M1–M4) โดยใช้ Qwen3-TTS ผ่าน MLX/mlx-audio รันแบบ local ล้วน ไม่มี web server, ไม่มี database, ไม่มี cloud call

## Tech Stack

- Python 3.10+, macOS Apple Silicon เท่านั้น (ต้องมี Metal/MLX)
- `mlx`, `mlx-audio` (git dependency, pin ที่ commit hash), `mlx-lm` — model inference
- `mlx-whisper` — speech-to-text ของ `/transcribe` (`discord_say_bot.py` / `stt_transcribe.py`)
- `discord.py[voice]` + `PyNaCl` — Discord bot (`discord_say_bot.py`)
- `ffmpeg` (external binary, ไม่ใช่ pip package) — แปลง MP3 และต่อไฟล์เสียงยาว
- `librosa`, `soundfile`, `soxr`, `pyloudnorm` — audio processing/loudness
- `typer-slim` (มีใน requirements.txt) และ stdlib `argparse` — CLI ของแต่ละ script ใช้ `argparse` ตรง ๆ ไม่ใช่ typer app
- stdlib `socket` + line-delimited JSON — daemon protocol (`tts_daemon.py`)
- `launchd` plist (`launchd/com.liino.qwen-tts-daemon.plist`) — ติดตั้งเป็น background service (ผู้ใช้ต้อง `launchctl load` เอง)
- `pytest` (`pytest==9.1.1` ใน requirements.txt) — test file `test_*.py` อยู่ที่ repo root, ไม่มี `pyproject.toml`/`pytest.ini`, ไม่มี `tests/` package (โฟลเดอร์ `tests/` มีแค่ fixture `.txt`), pytest auto-discover จาก root
- ไม่มี ORM/DB, ไม่มี web framework

## Functional Requirements

- Voice cloning จาก `voices/<name>.wav` (+ `voices/<name>.txt` เป็น reference transcript แบบ optional)
- Custom voice / voice design ผ่าน `--instruct` และ mood preset (`MOOD_PRESETS` ใน `qwen_clone_tts.py`, style "trait, trait, pacing" สั้น English)
- Language override: `--lang th|ja|en|...` (`LANG_CODES`/`resolve_lang` ใน `qwen_clone_tts.py`) — default `auto`; โมเดลไม่รองรับไทยใน `codec_language_id` ไทยยังใช้ `auto` (จาก TTS-1006)
- Interactive menu (`main.py`) และ non-interactive scripting CLI (`qwen_clone_tts.py`) ที่ report ผลผ่าน stdout/stderr + exit code (`OK <path>` / `ERROR: ...`)
- จำกัดข้อความไม่เกิน 300 ตัวอักษร (`MAX_CHARS`); โหมด `--stdin <input.txt> <output.wav>` อ่านจากไฟล์ แบ่ง chunk เองแล้วต่อเสียงเป็นไฟล์เดียว (ใช้เสียง Liino คงที่) — Hermes agent พึ่งพา path นี้
- แปลงเป็น MP3 ผ่าน ffmpeg ด้วย `--mp3`
- Background daemon (`tts_daemon.py`): โหลดโมเดลครั้งเดียว, FIFO queue, queue timeout, cache ตาม `(voice, text, instruct, lang)` — request เดิมที่ไม่มี `lang` hash เท่ากับ `lang="auto"` (cache เดิมยัง hit), idle unload, telemetry เป็น JSONL
- `qwen_clone_tts.py` ต้องตรวจจับ daemon อัตโนมัติและ fallback เป็นโหลดโมเดลเองถ้า daemon ไม่ทำงาน (ห้ามลบ fallback path นี้)
- Discord bot (`discord_say_bot.py`): slash command `/say` (พูดใน voice channel ด้วยเสียง Liino, รับหลายบรรทัด, auto mood จาก emoji ต่อบรรทัด, `mood:`/`language:` override) และ `/transcribe` (อัปโหลด `.mp3`/`.wav` → Whisper STT → ข้อความติด emoji mood พร้อม paste เข้า `/say file:`) — `/transcribe` ไม่แตะ TTS daemon
- Voice tuning helper (`tune_voice.py`) — ad-hoc A/B script (ไม่ใช่ test)

## Backend / Script Requirements

- Entry point อยู่ที่ root ของ repo ตรง ๆ ไม่มี `src/` package layout: `main.py`, `qwen_clone_tts.py`, `tts_daemon.py`, `tune_voice.py`, `discord_say_bot.py`, `stt_transcribe.py` + helper module `say_moods.py` / `transcribe_mood.py` (import โดย bot/CLI, ไม่ใช่ entry point)
- `qwen_clone_tts.py` เป็น single source of truth ของ constants (`MODEL_PATH`, `VOICES_DIR`, `MAX_CHARS`, `MOOD_PRESETS`, `LANG_CODES`, `chunk_text()`, `resolve_*`) — `tts_daemon.py` / `tune_voice.py` / `discord_say_bot.py` import จากมัน ห้าม duplicate
- โมเดลอยู่ที่ `models/<model-dir>` (ไม่ commit เข้า git — ดาวน์โหลดจาก HuggingFace เอง); default `models/Qwen3-TTS-12Hz-1.7B-Base-8bit`
- เสียงต้นแบบอยู่ที่ `voices/<name>.wav` (+ optional `.txt`); character preset อยู่ที่ `characters/`
- ไฟล์เสียงที่ generate แล้วอยู่ที่ `outputs/` (A/B run: `outputs/tuning/<run_id>/`); ของเก่า/สำรองอยู่ที่ `backups/`
- Config ของ daemon ทั้งหมดมาจาก environment variable เท่านั้น ไม่มี config file: `TTS_DAEMON_SOCK`, `TTS_CACHE_DIR`, `TTS_QUEUE_TIMEOUT`, `TTS_TELEMETRY_LOG`, `TTS_IDLE_UNLOAD`
- Config ของ Discord bot มาจาก environment variable เท่านั้น: `DISCORD_BOT_TOKEN` (required, secret, ไม่ auto-load จาก `.env`), `DISCORD_GUILD_ID`, `VC_IDLE_TIMEOUT_S`, `SAY_SENTENCE_GAP_S`, `TRANSCRIBE_WHISPER_MODEL`
- Daemon protocol: ส่ง JSON object เดียว + `\n` เป็น request, รับ JSON object เดียว + `\n` เป็น response ผ่าน Unix domain socket — hand-implement สองฝั่ง (`_try_daemon()` client / `handle_request()` daemon), เพิ่ม field ได้แต่ต้องคง backward compatible กับ `qwen_clone_tts.py` client เดิม
- `launchd/com.liino.qwen-tts-daemon.plist` เป็น template — แก้ path แล้วต้อง reinstall เอง (`launchctl load`) ไม่มี automation ให้
- Priority ของ daemon ทำผ่าน macOS Process QoS (`taskpolicy`) แบบ best-effort เท่านั้น ไม่ใช่ `nice` เชิงลบ (ต้อง root)

## Coding Conventions (รายละเอียดเพิ่มเติมดู `coding-style.md`)

- ไม่มี lint/format config ใน repo (ไม่มี ruff/black/pyproject.toml) — ยึดสไตล์เดิมของไฟล์ที่แก้เป็นหลัก
- มี `pytest` + `test_*.py` ที่ repo root: pure function (parsing, `resolve_lang`, `_cache_key`, `chunk_text`, emoji↔mood round-trip, `detect_mood` keyword) ต้องมี test และรัน `.venv/bin/python -m pytest -q` ให้เขียว; งานที่กระทบ audio/model/daemon runtime ต้อง manual validate ด้วยการรัน CLI/daemon/Discord จริงเพิ่ม
- Report ผลลัพธ์ CLI ผ่าน stdout/stderr text + exit code ตาม convention เดิม ไม่ใช้ `logging` module สำหรับ user-facing output (daemon telemetry ใช้ raw JSONL แยกต่างหาก)
