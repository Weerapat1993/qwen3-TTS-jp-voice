# Coding Style

## Python / Scripts

- Python 3.10+, ไม่มี formatter/linter config ที่ commit ไว้ (ไม่มี ruff/black/pyproject.toml/setup.cfg) — ยึดสไตล์ของไฟล์ที่กำลังแก้เป็นหลัก อย่าเปลี่ยน style ทั้งไฟล์โดยไม่จำเป็น
- ใส่ type hint กับ function ที่เพิ่ม/แก้ใหม่ (โค้ดเดิมใช้ `str | None`, `dict[str, str]` แบบ PEP 604/585 อยู่แล้ว)
- ไม่มี `src/` package layout — เก็บเป็น single-file script ที่ root ต่อไป เว้นแต่ผู้ใช้สั่งให้แตกเป็น module
- Comment ปนภาษาไทยกับอังกฤษได้ตามสไตล์เดิมของ repo (ดู `qwen_clone_tts.py`) — comment เฉพาะส่วนที่ซับซ้อนหรือมีเหตุผลที่ไม่ชัดจากโค้ด (เช่น trade-off, workaround)
- Constant ของ path/default/limit/preset ประกาศไว้ต้นไฟล์แบบ SCREAMING_CASE (`PROJ`, `VOICES_DIR`, `MODEL_PATH`, `MAX_CHARS`, `MOOD_PRESETS`, `LANG_CODES`) — `qwen_clone_tts.py` เป็น single source of truth; module อื่น (`tts_daemon.py`/`tune_voice.py`/`discord_say_bot.py`) import ไม่ duplicate
- CLI script ใช้ `argparse` ตรง ๆ (ไม่ใช้ typer แม้จะมี `typer-slim` อยู่ใน requirements.txt) ยกเว้น `main.py` ที่เป็น interactive menu; `discord_say_bot.py` ใช้ `discord.app_commands` (slash command)
- Mood preset (`MOOD_PRESETS`) instruct เขียน English สั้น style "trait, trait, pacing" ตรงตาม entry เดิม — อย่าใช้ ad-hoc `--instruct` แทนถ้าเพิ่ม tone ใหม่ที่ใช้ซ้ำได้ (ดู `CLAUDE.md`)
- ผลลัพธ์ CLI report ผ่าน stdout/stderr เป็น text ธรรมดา (`OK <path>` ตอนสำเร็จ, `ERROR: ...` ตอนล้มเหลว) พร้อม exit code ที่ถูกต้อง — ห้ามปล่อยให้ exception เดิม traceback ออกไปหา user โดยไม่ครอบ error message ก่อน
- Secret/token: TTS core (CLI/daemon) รัน local ไม่ต้องใช้ secret; `discord_say_bot.py` ต้องมี `DISCORD_BOT_TOKEN` — อ่านจาก environment variable เท่านั้น ห้าม hardcode หรือ commit (ไม่ auto-load จาก `.env`)

## Daemon (`tts_daemon.py`) / Protocol

- ใช้ stdlib `socket` + `json` เท่านั้น ไม่เพิ่ม async framework หรือ dependency ใหม่โดยไม่จำเป็น — คง FIFO queue / blocking loop เดิม
- Config ของ daemon มาจาก environment variable เท่านั้น (ไม่มี config file) — เพิ่ม env var ใหม่ต้อง: (1) มี default ที่ปลอดภัย (2) เอกสารไว้ในตาราง env var ของ `README.md`
- Request/response เป็น JSON object เดียว + `\n` ต่อข้อความ — hand-implement สองฝั่ง (`_try_daemon()` client / `handle_request()` daemon) แก้ต้องแก้คู่กัน; เพิ่ม field ใหม่ได้ แต่ห้าม breaking change กับ client เดิม (`qwen_clone_tts.py`)
- Cache key คือ `(voice, text, instruct, lang)` — request เดิมที่ไม่มี `lang` ต้อง hash เท่ากับ `lang="auto"` (cache เดิมยัง hit); ถ้าจะแก้ cache key logic ต้องระบุใน ticket/plan ชัดเจนว่า cache เดิมจะ invalidate
- Telemetry log (`TTS_TELEMETRY_LOG`) เป็น append-only JSONL หนึ่งบรรทัดต่อ request/cache-hit/error — ห้าม rotate/truncate เองแบบเงียบ ๆ

## ffmpeg / subprocess

- ทุกจุดที่เรียก `ffmpeg` หรือ external binary ต้องส่ง argument เป็น list ให้ `subprocess` โดยตรง ห้ามใช้ `shell=True` หรือ string interpolation เข้า shell command (กัน argv/shell injection โดยเฉพาะกับ path/text ที่มาจาก user input: `--stdin` file path, daemon request field, Discord message content)

## Discord bot (`discord_say_bot.py`) / helper modules

- ใช้ `discord.py[voice]` + `discord.app_commands`; command surface = `/say`, `/transcribe` — เปลี่ยน signature/choices ต้องอัปเดต README § Discord Bot และ restart bot ให้ Discord re-register
- `say_moods.py`: `EMOJI_MOOD` (emoji codepoint เดี่ยว → mood, ไม่มี ZWJ sequence), `MOOD_EMOJI` (mood → emoji ตัวแทน 1 ตัว; `default`/`long` จงใจไม่มี emoji) — เพิ่ม mood ต้องใส่ครบทั้งสอง map และ round-trip ผ่าน `extract_mood`
- `transcribe_mood.py`: `MOOD_KEYWORDS` เป็น list เรียงลำดับ, entry แรกที่ substring match ชนะ — วาง keyword ใหม่ให้ไม่แย่งเคสของ mood เดิม; `detect_mood()` ต้องคืน mood ที่ `MOOD_EMOJI` รู้จักเสมอ
- STT ผ่าน `mlx-whisper` local; `/transcribe` ไม่แตะ TTS daemon

## General

- ตั้งชื่อไฟล์ให้สื่อความหมาย (module ใช้ snake_case)
- ลบ code ที่ไม่ได้ใช้
- หลีกเลี่ยง duplicate logic
- เขียน comment เฉพาะส่วนที่ซับซ้อน
- ห้ามสร้าง documentation file ใหม่ถ้าไม่ได้รับคำสั่ง
- อัปเดต `README.md` เมื่อ CLI flag, environment variable, daemon protocol, mood/emoji map, หรือ Discord command เปลี่ยน

## Testing

- โปรเจกต์นี้มี `pytest` (`pytest==9.1.1` ใน requirements.txt) และ test file `test_*.py` ที่ repo root (`test_qwen_clone_tts.py`, `test_tts_daemon.py`, `test_say_moods.py`, `test_transcribe_mood.py`, `test_stt_transcribe.py`) — ไม่มี `pyproject.toml`/`pytest.ini`, ไม่มี `tests/` package (โฟลเดอร์ `tests/` มีแค่ fixture `.txt`), pytest auto-discover จาก root
- code change ที่มี pure function ทดสอบได้ (parsing, `resolve_lang`/`resolve_instruct`, `_cache_key`, `chunk_text`, emoji↔mood round-trip, `detect_mood` keyword, queue timeout math) **ต้อง** มี/อัปเดต test ใน `test_<module>.py` ที่ตรงกัน และรัน `.venv/bin/python -m pytest -q` ให้เขียว
- code change ที่กระทบ audio generation / model / daemon runtime / Discord playback ต้อง manual validate เพิ่ม:
  - CLI: `.venv/bin/python qwen_clone_tts.py --text "..." --out outputs/<file>.wav` → เช็ก `OK <path>` + เปิดไฟล์ฟังจริง
  - Daemon: start daemon (`.venv/bin/python tts_daemon.py`), ยิง request ผ่าน client จริง, เช็ก response JSON และบรรทัดใหม่ใน `TTS_TELEMETRY_LOG`
  - Discord: `/say` / `/transcribe` live ใน channel จริง
  - Mood A/B: `.venv/bin/python tune_voice.py` → ฟัง `outputs/tuning/<run_id>/` เทียบ mood ใกล้เคียง
- **Never use system `python3`** — ใช้ `.venv/bin/python` เสมอ (Python <3.10 ทำ CLI fail เงียบ ๆ)
- ห้ามลบ manual validation step เดิมโดยไม่ได้รับอนุมัติ

## Review Code

ใช้ skill `code-review` (เพิ่ม `security-review` เมื่อแตะ subprocess/ffmpeg invocation หรือ daemon socket input parsing จาก input ภายนอก) เป็น final review gate สำหรับ ticket TTS-XXXX

อ่าน:
- context/spec ที่อ้างใน ticket
- related script(s) (`main.py`/`qwen_clone_tts.py`/`tts_daemon.py`/`tune_voice.py`/`discord_say_bot.py`/`say_moods.py`/`transcribe_mood.py`/`stt_transcribe.py`)
- test ที่เกี่ยวข้อง (`test_*.py` ที่ repo root)
- README.md ส่วนที่เกี่ยวข้อง (CLI reference / daemon protocol / Discord bot / emoji map)
- manual validation ที่รันจริง (pytest + CLI/daemon/Discord run)

ให้ตอบเป็น:
- Verdict: PASS / NEEDS FIX / BLOCKED
- Findings เรียงตาม severity
- Missing tests / manual validation ถ้ามี
- Commands ที่ควรรัน (`.venv/bin/python -m pytest -q` + manual CLI/daemon run)
- ควรย้ายไป done ได้หรือยัง
