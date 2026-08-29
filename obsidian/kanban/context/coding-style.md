# Coding Style

## Python / Scripts

- Python 3.10+, ไม่มี formatter/linter config ที่ commit ไว้ (ไม่มี ruff/black/pyproject.toml/setup.cfg) — ยึดสไตล์ของไฟล์ที่กำลังแก้เป็นหลัก อย่าเปลี่ยน style ทั้งไฟล์โดยไม่จำเป็น
- ใส่ type hint กับ function ที่เพิ่ม/แก้ใหม่ (โค้ดเดิมใช้ `str | None`, `dict[str, str]` แบบ PEP 604/585 อยู่แล้ว)
- ไม่มี `src/` package layout — เก็บเป็น single-file script ที่ root ต่อไป เว้นแต่ผู้ใช้สั่งให้แตกเป็น module
- Comment ปนภาษาไทยกับอังกฤษได้ตามสไตล์เดิมของ repo (ดู `qwen_clone_tts.py`) — comment เฉพาะส่วนที่ซับซ้อนหรือมีเหตุผลที่ไม่ชัดจากโค้ด (เช่น trade-off, workaround)
- Constant ของ path/default/limit ประกาศไว้ต้นไฟล์แบบ SCREAMING_CASE (`PROJ`, `VOICES_DIR`, `MODEL_PATH`, `MAX_CHARS`)
- CLI script ใช้ `argparse` ตรง ๆ (ไม่ใช้ typer แม้จะมี `typer-slim` อยู่ใน requirements.txt) ยกเว้น `main.py` ที่เป็น interactive menu
- ผลลัพธ์ CLI report ผ่าน stdout/stderr เป็น text ธรรมดา (`OK <path>` ตอนสำเร็จ, `ERROR: ...` ตอนล้มเหลว) พร้อม exit code ที่ถูกต้อง — ห้ามปล่อยให้ exception เดิม traceback ออกไปหา user โดยไม่ครอบ error message ก่อน
- Secret/token: ปัจจุบันเครื่องมือนี้รันเฉพาะ local ไม่ต้องใช้ secret ใด ๆ — ถ้า ticket ไหนต้องเพิ่ม ให้มาจาก environment variable เท่านั้น ห้าม hardcode

## Daemon (`tts_daemon.py`) / Protocol

- ใช้ stdlib `socket` + `json` เท่านั้น ไม่เพิ่ม async framework หรือ dependency ใหม่โดยไม่จำเป็น — คง FIFO queue / blocking loop เดิม
- Config ของ daemon มาจาก environment variable เท่านั้น (ไม่มี config file) — เพิ่ม env var ใหม่ต้อง: (1) มี default ที่ปลอดภัย (2) เอกสารไว้ในตาราง env var ของ `README.md`
- Request/response เป็น JSON object เดียว + `\n` ต่อข้อความ — เพิ่ม field ใหม่ได้ แต่ห้าม breaking change กับ client เดิม (`qwen_clone_tts.py`)
- Cache key คือ `(voice, text, instruct)` — ถ้าจะแก้ cache key logic ต้องระบุใน ticket/plan ชัดเจนว่า cache เดิมจะ invalidate
- Telemetry log (`TTS_TELEMETRY_LOG`) เป็น append-only JSONL หนึ่งบรรทัดต่อ request/cache-hit/error — ห้าม rotate/truncate เองแบบเงียบ ๆ

## ffmpeg / subprocess

- ทุกจุดที่เรียก `ffmpeg` หรือ external binary ต้องส่ง argument เป็น list ให้ `subprocess` โดยตรง ห้ามใช้ `shell=True` หรือ string interpolation เข้า shell command (กัน argv/shell injection โดยเฉพาะกับ path/text ที่มาจาก user input)

## General

- ตั้งชื่อไฟล์ให้สื่อความหมาย (module ใช้ snake_case)
- ลบ code ที่ไม่ได้ใช้
- หลีกเลี่ยง duplicate logic
- เขียน comment เฉพาะส่วนที่ซับซ้อน
- ห้ามสร้าง documentation file ใหม่ถ้าไม่ได้รับคำสั่ง
- อัปเดต `README.md` เมื่อ CLI flag, environment variable, หรือ daemon protocol เปลี่ยน

## Testing

- โปรเจกต์นี้ยังไม่มี test suite (ไม่มี `pytest`, ไม่มี `tests/`, ไม่มี coverage target) — validate ด้วยการรันจริงแทน:
  - CLI: `python qwen_clone_tts.py --text "..." --out outputs/<file>.wav` แล้วเช็ก `OK <path>` + เปิดไฟล์ฟังจริง
  - Daemon: start daemon (`.venv/bin/python tts_daemon.py`), ยิง request ผ่าน client จริง, เช็ก response JSON และบรรทัดใหม่ใน telemetry log
- ถ้า ticket เพิ่ม logic ที่มี pure function ทดสอบได้ชัดเจน (parsing, cache key, queue timeout math) ให้พิจารณาเพิ่ม `tests/` + `pytest` เป็น dev dependency ใหม่ — ถือเป็นการตัดสินใจที่ต้องระบุใน `### Implementation Plan` เพราะเป็น infra ใหม่ของ repo ไม่ใช่ของที่มีอยู่แล้ว
- ห้ามลบ manual validation step เดิมโดยไม่ได้รับอนุมัติ

## Review Code

ใช้ skill `code-review` (เพิ่ม `security-review` เมื่อแตะ subprocess/ffmpeg invocation หรือ daemon socket input parsing) เป็น final review gate สำหรับ ticket TTS-XXXX

อ่าน:
- context/spec ที่อ้างใน ticket
- related script(s) (`main.py`/`qwen_clone_tts.py`/`tts_daemon.py`/`tune_voice.py`)
- README.md ส่วนที่เกี่ยวข้อง (CLI reference / daemon protocol)
- manual validation ที่รันจริง (ไม่มี automated test ให้เช็ก)

ให้ตอบเป็น:
- Verdict: PASS / NEEDS FIX / BLOCKED
- Findings เรียงตาม severity
- Missing manual validation ถ้ามี
- Commands ที่ควรรัน (manual CLI/daemon run)
- ควรย้ายไป done ได้หรือยัง
