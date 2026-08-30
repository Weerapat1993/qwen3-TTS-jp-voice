# Kanban Ticket Flow

ใช้ไฟล์นี้เป็น workflow กลางเมื่อสั่ง AI ให้ทำ ticket ใน `obsidian/kanban/tasks/`

## Product-Level Reference

โปรเจกต์นี้ไม่มี `prd.md` กลาง ใช้ `README.md` (root), `CLAUDE.md` (root) และ `README_HERMES.md` (root) เป็นแหล่งอ้างอิงภาพรวมของ scope, CLI reference, daemon protocol/config, Discord bot และ environment variables แทน โปรเจกต์นี้ไม่มี `AGENTS.md`, plugin system, permission system, database, หรือ web panel — entry point เป็น single-file script ที่ root ล้วน (`main.py`, `qwen_clone_tts.py`, `tts_daemon.py`, `tune_voice.py`, `discord_say_bot.py`, `say_moods.py`, `transcribe_mood.py`, `stt_transcribe.py`) ไม่มี `src/` package layout

ต้องอ่าน `CLAUDE.md`/`README.md` (และ `README_HERMES.md` ถ้าแตะ `--stdin`/daemon protocol) เมื่อ ticket หรือคำสั่งเกี่ยวข้องกับ:

- เพิ่ม/เปลี่ยน CLI flag หรือ behavior ของ `qwen_clone_tts.py` หรือ `main.py`
- แก้ daemon protocol, FIFO queue, queue timeout, cache key, idle-unload, หรือ telemetry ใน `tts_daemon.py` (protocol hand-implement สองฝั่ง: `_try_daemon()` ใน `qwen_clone_tts.py` กับ `handle_request()` ใน `tts_daemon.py` — แก้ต้องแก้คู่กัน และคง backward compatible กับ client เดิม)
- แก้เส้นทาง `--stdin <input.txt> <output.wav>` หรือ daemon protocol ที่ Hermes agent (external consumer, ดู `README_HERMES.md`) พึ่งพา
- เพิ่ม/เปลี่ยน environment variable ของ daemon (`TTS_DAEMON_SOCK`, `TTS_CACHE_DIR`, `TTS_QUEUE_TIMEOUT`, `TTS_TELEMETRY_LOG`, `TTS_IDLE_UNLOAD`) หรือวิธีติดตั้ง launchd service
- แก้วิธีประกอบ/รัน subprocess (`ffmpeg` concat/mp3, model load) จาก path/text ที่มาจาก user input
- เพิ่ม/เปลี่ยน mood preset (`MOOD_PRESETS` ใน `qwen_clone_tts.py`) หรือ emoji↔mood map (`say_moods.py`, `transcribe_mood.py`) — convention อยู่ใน `CLAUDE.md`
- เปลี่ยน Discord slash command surface ของ `discord_say_bot.py` (`/say`, `/transcribe`) — ดู README § Discord Bot
- review งานที่กระทบ module boundary ระหว่าง `qwen_clone_tts.py` (single source of truth ของ constants: `MODEL_PATH`, `VOICES_DIR`, `MAX_CHARS`, `MOOD_PRESETS`, `chunk_text()`, `resolve_*`) กับ importer ของมัน (`tts_daemon.py`, `tune_voice.py`, `discord_say_bot.py`)

ถ้า ticket หรือคำสั่งขัดกับ convention ใน `CLAUDE.md`/`coding-style.md` ให้เพิ่มหรืออัปเดต `### Open Questions` และถามผู้ใช้ว่าจะปรับ convention หรือให้ถือเป็น exception เฉพาะงานนั้น ห้ามเดาเองว่า convention เดิมหรือคำสั่งใหม่ถูกกว่า

## Board File

Board อยู่ในไฟล์เดียวที่ `obsidian/kanban/work-kanban-board.md` มี frontmatter `kanban-plugin: board` สำหรับให้ Obsidian render เป็น visual board และมี `## COLUMN` sections:

- `## BACKLOG` — ticket ที่ยังไม่เริ่ม
- `## TODO` — ticket ที่ plan แล้วและพร้อมเริ่ม
- `## PLAN` — ticket ที่กำลัง planning
- `## INPROGRESS` — ticket ที่กำลังทำอยู่
- `## REVIEW` — ticket ที่รอ review
- `## DONE` — ticket ที่เสร็จแล้ว
- `## CLOSED` — ticket ที่ยกเลิกหรือไม่ทำต่อ

Ticket รายใบต้องอยู่ใน:

- `obsidian/kanban/tasks/TTS-XXXX.md`

## Board Entry Format

ใน board file ให้ใช้รูปแบบ list item แบบนี้ภายใต้ `## COLUMN` section ที่ถูกต้อง:

```md
- [TTS-XXXX](tasks/TTS-XXXX.md): Ticket title
```

ห้ามเก็บรายละเอียด ticket เต็มใน board file ให้เก็บเฉพาะ link เท่านั้น

## Ticket File Format

Ticket file ต้องเป็น source of truth ของงานนั้นเสมอ ใช้ YAML frontmatter ตามตัวอย่างจริงใน `obsidian/kanban/tasks/TTS-1007.md`:

```md
---
ticket_id: TTS-XXXX
title: Ticket title
type: feature
status: todo
priority: high
notion_page_id: <เติมอัตโนมัติเมื่อ sync ขึ้น Notion — optional>
tags:
  - kanban/ticket
  - work
---

## 🟢 TTS-XXXX: Ticket title

Status: Todo
Priority: High
Source: <feedback/สถานการณ์ที่ทำให้เกิด ticket นี้ — หรือ Ref: link ไป issue/spec>

### Summary
...

### Context
...

### Scope
...

### Non-goals
...

### Acceptance Criteria
...

### Validation
...
```

Section ที่เพิ่มระหว่าง flow ตามสถานะ: `### Decisions` (จาก brainstorming/plan), `### Implementation Plan` (จาก `/kanban plan`), `### Open Questions`, `### Validation Results`, `### Review Notes`, `### Blocked Notes`, `### Done Notes`, `### Closed Notes`

กติกาสำคัญ:

- หนึ่ง ticket ต่อหนึ่งไฟล์เท่านั้น
- ชื่อไฟล์ต้องตรงกับ ticket id เช่น `obsidian/kanban/tasks/TTS-1007.md`
- `status:` ใน frontmatter และ `Status:` ใน body ต้องตรงกับ board ที่มี link ไปหา ticket นั้น
- ห้าม duplicate link ของ ticket เดียวกันไว้หลาย board section พร้อมกัน
- ห้ามย้ายหรือ rename ticket file เมื่อเปลี่ยนสถานะ ให้ย้ายเฉพาะ link ระหว่าง board sections

## Local Provider Commands

`kanban` skill อ้างถึงคำสั่งของ project ด้วย **operation name** กลาง ๆ เท่านั้น ตารางนี้คือ mapping ของ project นี้ (Python MLX TTS: single-file script ที่ repo root + Unix-socket daemon — ไม่มี framework CLI สำหรับ ticket sync) แทนที่ `TTS-XXXX` ด้วย ticket id จริง

| Operation | Command |
|---|---|
| `import-ticket` | จัดการผ่าน notion provider ตาม `.kanban.json` (`provider: notion`, `notionDataSourceId`, `notionStatusMap`) — ดู SKILL.md `Configuration` section และ provider branch ใน `cmd/create.md`/`cmd/move-review.md` ฯลฯ; ticket ที่ sync แล้วจะมี `notion_page_id` ใน frontmatter — ไม่มี local command เพิ่มเติม |
| `sync-ticket` | เช่นเดียวกับ `import-ticket` |
| `create-pr` | `gh pr create` (ดู skill `git-workflow-and-versioning` สำหรับ flow มาตรฐาน) |
| `sync-progress` | N/A — โปรเจกต์นี้ไม่มี dashboard/progress bar widget ที่ต้อง sync ให้ข้ามขั้นตอนนี้เงียบ ๆ |
| `lark-create` | N/A — ยังไม่มี `lark-cli` หรือ Lark task config ผูกกับ repo นี้ |
| `lark-rename` | N/A เช่นเดียวกัน |
| `lark-move` | N/A เช่นเดียวกัน |
| `lark-help` | ใช้ `lark-cli --help` ตรง ๆ ถ้าผู้ใช้ติดตั้งไว้ระดับเครื่อง |

Lark task config: โปรเจกต์นี้ไม่มี environment variable สำหรับ Lark tasklist ผูกไว้ ถ้าผู้ใช้ต้องการเปิดใช้ optional Lark sync ต้อง setup `lark-cli` และ tasklist config เองก่อน

### post-implementation

หลัง implement เสร็จใน `/kanban start` ให้เช็กว่า ticket แตะสิ่งที่ต้องอัปเดตคู่กันหรือไม่ ก่อนรัน validation ของ ticket:

1. ถ้า ticket เพิ่ม/เปลี่ยน environment variable ใหม่ (ของ daemon หรือ Discord bot) ให้อัปเดต `README.md` (§ Daemon `Config (environment variables)` หรือ § Discord Bot `Config`) และ `CLAUDE.md` คู่กับโค้ดเสมอ
2. ถ้า ticket เปลี่ยน CLI flag, daemon protocol/response shape, หรือ mood/emoji map ให้อัปเดต `README.md` (§ CLI Reference / § Daemon `Protocol` / § Discord Bot `Emoji → mood map`) ให้ตรงกับพฤติกรรมใหม่
3. โปรเจกต์นี้ไม่มี database, migration, หรือ seeder — ข้ามขั้นตอนนี้เงียบ ๆ เสมอ
4. ถ้า ticket เปลี่ยนวิธีติดตั้ง daemon เป็น service (`launchd/com.liino.qwen-tts-daemon.plist`, path, `RunAtLoad`/`KeepAlive`) ให้อัปเดต plist template + README § Daemon และ `README_HERMES.md` § 5

### Deployment Report

ตอน report ผลของ `/kanban start` ต้องบอกสิ่งที่ผู้ใช้ต้องทำเมื่อ deploy/reinstall:

- ระบุถ้ามี environment variable ใหม่ที่ต้องตั้งจริง (`TTS_*` ของ daemon หรือ `DISCORD_BOT_TOKEN` ฝั่ง bot)
- ระบุถ้ามี dependency ใหม่ที่ต้อง `.venv/bin/pip install -r requirements.txt`
- ระบุถ้าต้อง reinstall launchd service (`launchctl unload ... && launchctl load ...`) เพราะ path/plist เปลี่ยน
- ระบุถ้าต้อง restart daemon (`.venv/bin/python tts_daemon.py`) เพราะแก้ logic ในตัว daemon เอง — แต่ถ้าแก้แค่ constant ที่ client resolve เอง (เช่น `MOOD_PRESETS`) daemon ไม่ต้อง restart
- ระบุถ้าต้อง restart Discord bot (`discord_say_bot.py` / `run_say_bot.sh`) เพราะ slash command surface หรือ `MOOD_PRESETS` dropdown เปลี่ยน
- ระบุชัดเจนเมื่อไม่ต้องทำอะไรเลยตอน deploy

## Optional Lark Ticket Command Sync

Lark Ticket Command sync เป็น optional layer เท่านั้น; `obsidian/kanban/tasks` Markdown ticket files และ `obsidian/kanban/work-kanban-board.md` ยังเป็น source of truth เสมอ

ใช้ `obsidian/kanban/tasks/lark-sync.json` เป็น local preference file:

```json
{
  "enabled": false
}
```

ถ้าไฟล์ไม่มีอยู่ ให้ถือว่า sync ปิดอยู่ (ค่า default ของโปรเจกต์นี้คือปิด)

รองรับคำสั่ง workflow เหล่านี้:

```txt
/kanban lark status
/kanban lark enable
/kanban lark disable
/kanban lark sync TTS-XXXX
```

กติกา:

- `/kanban lark enable` เขียน `"enabled": true` ลง `obsidian/kanban/tasks/lark-sync.json` และนับเป็นการยืนยันว่าเปิด sync — แจ้งผู้ใช้ด้วยว่าโปรเจกต์นี้ยังไม่มี local command สำหรับ lark-create/rename/move จริง ต้องใช้ `lark-cli` ตรง ๆ
- `/kanban lark disable` เขียน `"enabled": false`
- `/kanban lark status` รายงาน preference และ `lark-cli` ที่ตรวจได้
- `/kanban lark sync TTS-XXXX` ใช้ backfill ticket ที่มีอยู่ local แล้วแต่ยังไม่ขึ้น Lark board — เนื่องจากไม่มี local command ให้แจ้งผู้ใช้ว่าต้องทำผ่าน `lark-cli` เอง
- ถ้า sync ปิดอยู่หรือไฟล์หาย ให้ skip Lark แล้วทำ local flow ต่อ
- Lark sync failure ห้ามเปลี่ยนหรือ revert local board state แบบเงียบ ๆ

## Canonical Kanban Command Mapping

ทุก agent และทุก profile (`liino`, `sonnet`, `deepseek-flash`) ต้องตีความชื่อขั้นตอนในคำสั่งของผู้ใช้ตาม mapping เดียวกันนี้ และต้องเรียกใช้คำสั่งตามรูปแบบที่ระบุ ห้ามแทนชื่อขั้นตอนด้วยคำสั่งอื่น:

| ขั้นตอนที่ผู้ใช้ระบุ | คำสั่ง Kanban ที่ต้องใช้ |
|---|---|
| `plan` | `/kanban plan TTS-XXXX` |
| `start` | `/kanban start TTS-XXXX` |
| `move-review` | `/kanban move-review TTS-XXXX` |
| `review` | `/kanban review TTS-XXXX` |
| `done` | `/kanban done TTS-XXXX` |

กติกาการตีความ:

1. เมื่อผู้ใช้ระบุลำดับ เช่น `plan -> start -> move-review -> review -> done` ให้ดำเนินการตามลำดับนี้เท่านั้น และห้ามข้ามขั้นโดยอ้างว่า implementation ผ่านแล้ว
2. ถ้าผู้ใช้ระบุ `start` ให้ถือว่าเป็นการเรียก `/kanban start TTS-XXXX` ไม่ใช่เพียงการเริ่มแก้ไฟล์ด้วย Git
3. `move-review` เป็นขั้นแยกจาก `start` และต้องใช้ `/kanban move-review TTS-XXXX` เท่านั้น โดยต้องทำ GitHub handoff/PR ตาม Review Gate ด้านล่าง
4. `review` เป็นขั้นตรวจสอบหลัง ticket อยู่ใน Review และต้องใช้ `/kanban review TTS-XXXX` ก่อนการตัดสิน PASS/NEEDS FIX/BLOCKED
5. `done` ทำได้เฉพาะหลัง Review Gate ได้ `PASS` และต้องใช้ `/kanban done TTS-XXXX`
6. ถ้าคำสั่งที่ผู้ใช้ระบุขัดกับสถานะ ticket หรือมี dependency/blocker ให้หยุดที่ขั้นนั้นและรายงาน blocker อย่างชัดเจน ห้ามเลื่อนสถานะเอง
7. ในรายงานทุกขั้น ให้ระบุคำสั่ง Kanban ที่ถูกใช้จริงและหลักฐานของผลลัพธ์ ห้ามรายงานจากเจตนาหรือแผนที่ยังไม่ได้ดำเนินการ

## Flow

### 1. Create Ticket

เมื่อสร้าง ticket ใหม่:

1. ใช้ `using-superpowers` เพื่อเลือก skill ที่เหมาะกับ ticket นี้
2. อ่าน `CLAUDE.md` และ `README.md` ถ้างานแตะ CLI flag, daemon protocol, subprocess/ffmpeg, mood preset, หรือ Discord bot; ข้ามได้ถ้าเป็นงาน copy-only/board-only
3. ใช้ `brainstorming` ถ้า requirement ยังไม่ชัด, มีหลายแนวทาง, ต้องแตก scope, หรือชนกับ convention เดิม
4. สร้าง `obsidian/kanban/tasks/TTS-XXXX.md` พร้อม frontmatter (`ticket_id`, `title`, `type`, `status: backlog`, `priority`, `tags`), `Status: Backlog`, priority, summary, context, scope, non-goals, acceptance criteria, และ validation
5. เพิ่ม link ของ ticket ใน `obsidian/kanban/work-kanban-board.md (## BACKLOG)`
6. ถ้า optional Lark sync เปิดอยู่ ให้แจ้งผู้ใช้ว่าต้อง backfill ผ่าน `lark-cli` เอง (ไม่มี local command อัตโนมัติ)

ห้ามสร้าง ticket เป็น block ยาวใน `obsidian/kanban/work-kanban-board.md (## BACKLOG)`

### 2. Start Ticket

เมื่อผู้ใช้สั่งให้เริ่มทำ ticket:

> การสั่งงาน Sonnet ต้องเริ่มด้วย prompt `/kanban start TTS-XXXX` เป็นอันดับแรกเสมอ

1. หา link ของ ticket จาก board file ปัจจุบัน โดยปกติคือ `obsidian/kanban/work-kanban-board.md (## PLAN)`, `(## BACKLOG)` หรือ `(## TODO)`
2. อ่าน ticket file จาก `obsidian/kanban/tasks/TTS-XXXX.md`
3. อ่าน `CLAUDE.md`/`README.md`/`README_HERMES.md` เมื่อ ticket เข้าเงื่อนไข Product-Level Reference ด้านบน
4. อ่าน context, related script(s) (`qwen_clone_tts.py`/`tts_daemon.py`/`main.py`/`discord_say_bot.py`/`say_moods.py`/`transcribe_mood.py`/`tune_voice.py`), test ที่เกี่ยวข้อง (`test_qwen_clone_tts.py`/`test_tts_daemon.py`/`test_say_moods.py`/`test_transcribe_mood.py`/`test_stt_transcribe.py`) และ acceptance criteria ที่ ticket อ้างถึง
5. ถ้า ticket ขัดกับ convention ใน `CLAUDE.md`/`coding-style.md` และผู้ใช้ยังไม่ approve exception ให้เพิ่มหรืออัปเดต `### Open Questions` และหยุดก่อนย้ายเข้า `In Progress`
6. ถ้า ticket มี `### Implementation Plan` และ `Status: Plan` แล้ว ให้เริ่มต่อได้ทันทีโดยไม่เรียก `writing-plans` ซ้ำ
7. ถ้า ticket อยู่ `Status: Backlog` สามารถข้าม `Plan` และย้ายเข้า `In Progress` ได้ทันทีเมื่อครบทุกเงื่อนไขนี้:
   - acceptance criteria ชัดเจน
   - context ที่จำเป็นมีครบ หรือไม่จำเป็นต่อการตัดสินใจ
   - ไม่มี `### Open Questions` หรือ blocking notes ที่ยังไม่ resolved
   - งานเล็ก ความเสี่ยงต่ำ และไม่เข้าเกณฑ์ที่ควรใช้ `writing-plans` ตาม Plan Ticket flow
8. ถ้า backlog ticket ไม่ครบทุกเงื่อนไขสำหรับการข้าม `Plan` ให้ทำ Plan Ticket flow ก่อน และหยุดถ้า plan ทำให้เกิด `Open Questions`
9. ใช้ skill `using-superpowers` เพื่อเลือก skill ที่เหมาะกับงานก่อนเริ่ม implement
10. ก่อนแก้ไขไฟล์ใด ๆ ต้องสร้างและ checkout branch `feature/TTS-XXXX` จาก `main` (หรือ `bugfix/TTS-XXXX` / ชื่อ branch ที่ผู้ใช้ระบุ) และตรวจสอบด้วย `git branch --show-current`; ห้าม implement บน `main`
11. ย้ายเฉพาะ link ของ ticket ไป `obsidian/kanban/work-kanban-board.md (## INPROGRESS)`
12. เปลี่ยน `Status:`/`status:` ใน ticket file เป็น `In Progress`/`inprogress`
13. ทำงานตาม scope และ acceptance criteria โดยให้ skill kanban start จัดการ test และ validation ที่เกี่ยวข้อง ไม่ต้องสั่งตรวจ test/validation ซ้ำแยกต่างหาก
14. เมื่อ implementation และ validation ผ่านแล้ว ให้ commit งานบน feature branch และเตรียม branch สำหรับ review; ห้ามอ้างว่าเริ่มงานบน branch ถูกต้องหากยังไม่ได้ตรวจสอบจริง
15. หลัง skill kanban start จบ ให้ report ผลงานและบอกว่า ticket พร้อม review หรือยัง
16. ห้ามย้าย ticket ไป `Review` อัตโนมัติระหว่างคำสั่ง `start` แม้ implementation และ validation จะผ่านแล้ว
17. ต้องรอคำสั่ง `/kanban move-review TTS-XXXX` แบบ explicit ก่อน จึงค่อยเพิ่ม `Review Notes`, ย้าย board link ไป `(## REVIEW)`, และเปลี่ยน `Status:` เป็น `Review`

ห้ามเริ่ม implement หาก ticket ไม่มี acceptance criteria หรือ context ที่จำเป็นต่อการตัดสินใจ

### 2A. Plan Ticket

เมื่อผู้ใช้สั่งให้ plan ticket ก่อนเริ่มงาน:

1. หา ticket file จาก `obsidian/kanban/tasks/TTS-XXXX.md` และอ่าน context/AC/validation ที่จำเป็น
2. อ่าน `CLAUDE.md`/`README.md`/`README_HERMES.md` เมื่อ ticket เข้าเงื่อนไข Product-Level Reference ด้านบน
3. ใช้ skill `using-superpowers` เพื่อเลือก skill ที่เหมาะกับการวางแผน
4. แสดง pre-plan assessment สั้น ๆ: status/board ปัจจุบัน, ควรใช้ `brainstorming` หรือไม่, ควรใช้ `writing-plans` หรือไม่, convention alignment (`CLAUDE.md`/`coding-style.md`), และไฟล์/สถานะที่จะเปลี่ยน (โปรเจกต์นี้ไม่มี web panel UI — ข้าม UI design gate ใด ๆ เสมอ; งาน mood ที่ต้องพิสูจน์ว่าโมเดลออกเสียงต่างจริง ต้องมี A/B validate ด้วย `tune_voice.py` เป็น gate ก่อน)
5. ถามผู้ใช้ด้วย `Yes` / `No` ว่าจะ plan ต่อหรือไม่; ถ้า `No` ให้หยุด
6. ถ้า context ยังไม่พอ หรือ ticket ขัดกับ convention เดิมและยังไม่ได้รับ approval ให้เพิ่ม `### Open Questions` แล้วหยุด
7. ถ้า `brainstorming` ถูกแนะนำ ให้ใช้เพื่อ clear scope / approach / decision ที่สำคัญ; ถ้าทำให้ยังตอบไม่ได้ ให้หยุดและบันทึก `Open Questions`
8. ถ้า `writing-plans` ถูกแนะนำ ให้ใช้หลัง `brainstorming` resolved แล้ว; ถ้าไม่ถูกแนะนำ ให้เขียน plan แบบ concise ได้เลย
9. เพิ่มหรืออัปเดต `### Implementation Plan` โดยใส่ context, planned changes, files likely to change (`qwen_clone_tts.py`/`tts_daemon.py`/`main.py`/`discord_say_bot.py`/`say_moods.py`/`transcribe_mood.py`/`tune_voice.py`/`test_*.py`/`README.md`/`CLAUDE.md`), validation commands (`.venv/bin/python -m pytest -q` + manual CLI/daemon run ที่จำเป็น), และ risks / decisions
10. ย้ายเฉพาะ link ของ ticket ไป `obsidian/kanban/work-kanban-board.md (## PLAN)` และเปลี่ยน `Status:` เป็น `Plan`
11. ห้าม implement code changes ระหว่างคำสั่ง plan

แนะนำ `brainstorming` เมื่อ requirement ยังไม่ชัด, มีหลาย approach, มี `Open Questions`, ต้องแตก scope, มี tension กับ convention เดิม, หรือมี decision สำคัญที่ไม่ควรเดาระหว่าง implementation

แนะนำ `writing-plans` เมื่อ ticket แตะทั้ง `qwen_clone_tts.py` และ `tts_daemon.py` พร้อมกัน, เปลี่ยน daemon protocol / cache key / env var contract, เปลี่ยนเส้นทาง `--stdin`/Hermes, หรือมี regression risk ชัดเจน; งาน copy-only, board-only, documentation-only, single-file low-risk, หรือเพิ่ม mood preset ตรง ๆ ใช้ plan แบบ concise ได้

เมื่อผู้ใช้สั่ง `start`:

1. ถ้ามี `### Implementation Plan` และ `Status: Plan` แล้ว ให้ดำเนิน Start Ticket ต่อ
2. ถ้าอยู่ `Backlog` และครบเงื่อนไขข้าม `Plan` ให้ย้ายเข้า `In Progress` ได้เลย
3. ถ้ายังไม่มี plan หรือ plan ยังมี `Open Questions` ให้กลับมาทำ Plan Ticket ก่อน

### 3. Superpowers Gate

ใช้ skill เหล่านี้เป็น workflow helper ระหว่างทำ ticket โดยไม่แทนที่ `CLAUDE.md`, tests, หรือ review gates ของ repo นี้

Skill map:

- `using-superpowers`: ขั้นแรกของทุก ticket
- `brainstorming`: requirement ยังคลุมเครือ, ต้องเลือก approach, หรือแตกงานจาก scope ใหญ่เกินไป
- `writing-plans`: `/kanban plan` เมื่อ pre-plan assessment แนะนำ
- `systematic-debugging` / `debugging-and-error-recovery`: bug/debug gate สำหรับ repro, trace, isolate root cause เมื่อ test fail, bug ยังไม่ชัด, behavior ไม่ตรง AC, เจอ subprocess/model/daemon runtime error, หรือเสียงที่ generate ออกมาผิด (`TTS chunk 1 produced no final audio`, daemon ตอบ `no audio produced`)
- `code-review`: outsider review gate สำหรับ plan/diff/code change ที่มี regression risk หรือแตะ module boundary ระหว่าง `qwen_clone_tts.py` (shared constants) กับ importer (`tts_daemon.py`/`tune_voice.py`/`discord_say_bot.py`) หรือแตะ daemon protocol
- `security-review`: เพิ่มเติมจาก `code-review` เฉพาะเมื่อ ticket เปลี่ยนวิธีประกอบ subprocess argv (ffmpeg / model load) จาก input ภายนอก หรือวิธี parse daemon socket request (risk: argv/shell injection ผ่าน user text, `--stdin` file path, หรือ daemon request field `text`/`instruct`/`voice`/`lang`)

เกณฑ์ขั้นต่ำ:

- Ticket เล็กและชัดเจน: ใช้ `using-superpowers` อย่างน้อยหนึ่งครั้งก่อนเริ่ม
- Ticket ที่ไม่ชัด: ใช้ `brainstorming` ก่อน finalize scope, AC หรือ `### Implementation Plan`
- Ticket เสี่ยงหรือ context ไม่พอ: ผ่าน `/kanban plan` ก่อน `/kanban start`
- Bug report / regression / test fail / runtime fail / เสียงผิด: ใช้ `systematic-debugging` หรือ `debugging-and-error-recovery` ก่อนเสนอ fix
- Plan/diff/code change เสี่ยงหรือแตะ module boundary / daemon protocol: ใช้ `code-review`
- Ticket ที่เปลี่ยนวิธีประกอบ subprocess command หรือ parse daemon input จาก input ภายนอก: เพิ่ม `security-review`

ถ้าใช้ skill เหล่านี้ระหว่าง ticket ให้บันทึกสั้น ๆ ใน `Review Notes` หรือ `Done Notes` ว่าใช้ skill ใดและช่วยตัดสินใจเรื่องอะไร

### 4. Implementation Gate

ระหว่างทำ ticket ต้องปฏิบัติตาม:

- `CLAUDE.md` (root)
- `obsidian/kanban/context/requirements.md`
- `obsidian/kanban/context/coding-style.md`
- Existing project conventions: module boundary (`qwen_clone_tts.py` = single source of truth ของ constants ↔ importer), daemon protocol backward-compat + hand-implement สองฝั่ง, daemon config มาจาก env var เท่านั้น (ไม่มี config file), `OK <path>` / `ERROR: ...` stdout/stderr contract + exit code, ffmpeg/subprocess ส่ง argv เป็น list เสมอ (ห้าม `shell=True`), mood preset style "trait, trait, pacing" สั้น English

**Never use system `python3`** — ใช้ `.venv/bin/python` เสมอ (ดู `CLAUDE.md`); Python <3.10 ทำ CLI fail แบบเงียบ ๆ (`TTS chunk 1 produced no final audio`)

การทดสอบ:

- โปรเจกต์นี้มี `pytest` (`requirements.txt`) และ test file `test_*.py` ที่ repo root — ไม่มี `tests/` package, ไม่มี `pyproject.toml`, pytest auto-discover จาก root
- code change ที่มี pure function ทดสอบได้ชัดเจน (parsing, `resolve_lang`/`resolve_instruct`, `_cache_key`, `chunk_text`, emoji↔mood round-trip, `detect_mood` keyword, queue timeout math) **ต้อง** มี test ใน `test_<module>.py` ที่ตรงกัน และรัน `.venv/bin/python -m pytest -q` ให้เขียว
- code change ที่กระทบ audio generation / model / daemon runtime ต้อง manual validation ด้วย:
  - CLI: `.venv/bin/python qwen_clone_tts.py --text "..." --out outputs/<file>.wav` → เช็ก `OK <path>` + เปิดไฟล์ฟังจริง
  - Daemon: start daemon (`.venv/bin/python tts_daemon.py`), ยิง request ผ่าน client จริง, เช็ก response JSON และบรรทัดใหม่ใน `TTS_TELEMETRY_LOG`
  - Discord (ถ้าแตะ bot): `/say` / `/transcribe` live ใน channel จริง
- โปรเจกต์นี้ไม่มี lint/format command (ไม่มี ruff/black/mypy/Makefile/pyproject) — ห้ามอ้างอิงคำสั่งที่ไม่มีจริง
- ห้ามลบ manual validation step เดิมโดยไม่ได้รับอนุมัติ

หาก test fail และสาเหตุยังไม่ชัด ให้ใช้ skill `systematic-debugging` เพื่อแยก root cause ก่อนแก้ไข

หากเป็น bug report, regression, หรือ behavior ที่ผู้ใช้แจ้งว่า "เสีย", "ไม่ทำงาน", "เสียงผิด", "error", "throwing", "failing" ให้ใช้ skill `debugging-and-error-recovery` หรือ `systematic-debugging` ตั้งแต่เริ่ม debug เว้นแต่ผู้ใช้บอกให้ข้าม แต่ยังต้องทำตามขั้นตอน repro → trace → falsify ภายในงานนั้น

### 5. Move To Review

เมื่อ implementation ผ่าน:

1. เพิ่ม `Review Notes` แบบสั้นใน ticket file
2. ย้าย link จาก `obsidian/kanban/work-kanban-board.md (## INPROGRESS)` ไป `(## REVIEW)`
3. เปลี่ยน `Status:`/`status:` เป็น `Review`/`review`

ตัวอย่าง `Review Notes`:

```md
### Review Notes
- Files: `qwen_clone_tts.py`, `say_moods.py`, `test_say_moods.py`
- Commands: `.venv/bin/python -m pytest -q` (59 passed), `.venv/bin/python qwen_clone_tts.py --text "..." --mood pouty --out outputs/pouty.wav` → OK + ฟัง
- Deploy: ไม่มี env/dep ใหม่; daemon ไม่ต้อง restart; `discord_say_bot.py` ต้อง restart ให้ dropdown อัปเดต
- Skills: `using-superpowers`, `writing-plans`
```

### 6. Review Gate

ก่อนหรือพร้อมกับการย้าย ticket เข้า `## REVIEW` ต้องทำ GitHub handoff ให้ตรวจสอบได้:

1. ตรวจสอบว่าอยู่บน feature branch `feature/TTS-XXXX` หรือ `bugfix/TTS-XXXX` (หรือชื่อ branch ที่ผู้ใช้ระบุ) และไม่ใช่ `main`
2. commit งานที่พร้อม review และ push branch ด้วย `git push -u origin HEAD`
3. สร้าง pull request ด้วย `gh pr create` ตาม operation `create-pr` ของโปรเจกต์ โดยตั้ง base เป็น `main` และใส่ ticket id, summary, test/validation evidence และ review scope
4. อ่านผลลัพธ์หรือใช้ `gh pr view` เพื่อยืนยันว่า PR ถูกสร้างจริง พร้อมบันทึก URL/number ใน `Review Notes`
5. ถ้า push หรือสร้าง PR ไม่สำเร็จ ให้เพิ่ม `Blocked Notes` และห้ามรายงานว่า move-review เสร็จสมบูรณ์

ห้ามข้าม PR โดยปริยาย แม้ implementation และ test จะผ่านแล้ว เว้นแต่ผู้ใช้อนุมัติ no-PR exception อย่างชัดเจน

หลัง ticket อยู่ใน `obsidian/kanban/work-kanban-board.md (## REVIEW)`:

> การ review ต้องเริ่มด้วยการสั่ง Sonnet ด้วย prompt `/kanban review TTS-XXXX` เป็นอันดับแรกเสมอ

- ใช้ `code-review` ถ้างานมี plan, แตะ module boundary `qwen_clone_tts.py` ↔ importer, แตะ daemon protocol, regression risk, หรือผู้ใช้ขอ review โดยตรง แต่ห้ามเรียกคำสั่ง `/code-review` เกิน 2 ครั้งต่อ ticket; หลังจากครบ 2 ครั้ง ให้ใช้ manual test เป็น review gate แทน
- ใช้ `security-review` เพิ่มเมื่อเปลี่ยนวิธีประกอบ subprocess argv (ffmpeg/model) จาก input ภายนอก หรือวิธี parse daemon socket request
- Manual test หลังครบโควตา `/code-review` ต้องตรวจ acceptance criteria, diff, regression, security ที่เกี่ยวข้อง, validation output (pytest + CLI/daemon run จริง) และสถานะ ticket/board โดยห้ามอ้างผลจากคำกล่าวอ้างของ agent เพียงอย่างเดียว
- งานเล็กและ low-risk ใช้ lightweight review โดยเช็ก AC, scope, test, และไม่มี obvious regression

ให้ผลลัพธ์เป็น:

```md
Review type: Lightweight / code-review / security-review
Verdict: PASS / NEEDS FIX / BLOCKED

Findings:
- ...

Missing tests:
- ...

Commands run:
- ...

Move to done: Yes / No
```

ถ้า `NEEDS FIX`:

1. แก้ issue ทันที
2. รัน test ที่เกี่ยวข้องอีกครั้ง (`.venv/bin/python -m pytest -q` + manual CLI/daemon run ที่เกี่ยวข้อง)
3. ใช้ `systematic-debugging` หรือ `debugging-and-error-recovery` เมื่อ root cause ยังไม่ชัด
4. Review ซ้ำด้วย gate เดิม หรืออัปเกรดเป็น `security-review` หาก fix ทำให้งานมี security impact
5. ห้ามย้ายไป done จนกว่า verdict เป็น `PASS`

ถ้า `BLOCKED`:

1. เก็บ link ของ ticket ไว้ใน `(## REVIEW)`
2. เพิ่ม `Blocked Notes` ใน ticket file
3. ระบุสิ่งที่ต้องการจากผู้ใช้หรือ dependency ที่ขาด

### 7. Move To Done

เมื่อ Review Gate ให้ verdict `PASS`:

> การย้ายไป Done ต้องเริ่มด้วยการสั่ง Sonnet ด้วย prompt `/kanban done TTS-XXXX` เป็นอันดับแรกเสมอ

1. เพิ่ม `Done Notes` แบบสั้นใน ticket file (รวม root cause ถ้าเป็น bugfix — โปรเจกต์นี้ไม่มี skill `post-mortem` แยก ให้บันทึกสั้น ๆ ตรงนี้แทน)
2. ย้าย link จาก `(## REVIEW)` ไป `(## DONE)`
3. เปลี่ยน `Status:`/`status:` เป็น `Done`/`done`
4. ถ้า optional Lark sync เปิดอยู่ ให้แจ้งผู้ใช้ backfill ผ่าน `lark-cli` เอง (ไม่มี local command อัตโนมัติ)

ตัวอย่าง `Done Notes`:

```md
### Done Notes
- Review Gate: PASS
- Gates passed: lightweight review, tests
- Validation: `.venv/bin/python -m pytest -q` + manual CLI/daemon run
- Root cause (ถ้าเป็น bugfix): ...
```

### 8. Close Or Archive Ticket

ใช้ `obsidian/kanban/work-kanban-board.md (## CLOSED)` เฉพาะ ticket ที่ยกเลิกหรือไม่ต้องทำต่อ

เมื่อ close ticket:

1. เพิ่ม `Closed Notes` ใน ticket file
2. ย้ายเฉพาะ link ของ ticket จาก board ปัจจุบันไป `(## CLOSED)`
3. เปลี่ยน `Status:`/`status:` ใน ticket file เป็น `Closed`/`closed`
4. ระบุเหตุผลที่ปิด เช่น duplicate, obsolete, out of scope, model แยกเสียงไม่ได้ (mood ticket), หรือ replaced by ticket อื่น

### 9. Close Sprint

เมื่อผู้ใช้สั่ง `/kanban sprint close` หรือ `/kanban sprint close --name=splint-X`:

1. อ่าน `obsidian/kanban/work-kanban-board.md` และรวบรวม entries ทั้งหมดใน `## DONE` และ `## CLOSED`
2. ถ้าทั้งสอง section ว่างเปล่า ให้ report ว่าไม่มีอะไร archive และหยุด
3. กำหนดชื่อ splint file ใหม่:
   - ถ้ามี `--name=` ให้ใช้ค่านั้น (เช่น `splint-3`)
   - ถ้าไม่มี ให้ scan ไฟล์ `obsidian/kanban/splint-*.md` ที่มีอยู่ หาเลขสูงสุด แล้ว +1
4. สร้าง `obsidian/kanban/splint-N-kanban-board.md` ด้วย format ที่มีเฉพาะ `## DONE` และ `## CLOSED` sections พร้อม links จากข้อ 1
5. ลบ entries ของ tickets ที่ archive แล้วออกจาก `## DONE` และ `## CLOSED` ใน `work-kanban-board.md`
6. ห้ามแตะ sections อื่น (`## BACKLOG`, `## TODO`, `## PLAN`, `## INPROGRESS`, `## REVIEW`) — tickets ที่ยังค้างอยู่ที่เดิมโดยอัตโนมัติ
7. ห้ามย้ายหรือ rename ticket files ใน `obsidian/kanban/tasks/`
8. ห้ามเปลี่ยน `Status:`/`status:` ใน ticket files ใดๆ ทั้งสิ้น
9. แสดงผลสรุป: ชื่อไฟล์ splint archive ที่สร้าง, tickets ที่ถูก archive, tickets ที่ยังคงอยู่บน active board

Format ของ splint archive file:

```md
---

kanban-plugin: board

---

## DONE

- [TTS-XXXX](tasks/TTS-XXXX.md): Ticket title


## CLOSED

- [TTS-XXXX](tasks/TTS-XXXX.md): Ticket title

%% kanban:settings
{"kanban-plugin":"board","list-collapse":[false,false]}
%%
```

## Operating Rules

- Board files เก็บเฉพาะ heading และ list item link เท่านั้น
- Ticket file เป็น source of truth ของรายละเอียดทั้งหมด
- ย้ายสถานะด้วยการย้าย link ระหว่าง board sections และอัปเดต `Status:`/`status:` ใน ticket file
- ห้าม duplicate ticket link ไว้หลาย board section พร้อมกัน
- ห้ามเปลี่ยน path ของ ticket file ระหว่าง flow ปกติ
- ห้ามย้าย ticket ไป done หาก review verdict ไม่ใช่ `PASS` หรือยังขาด test ที่จำเป็น
- ใช้ `security-review` เฉพาะ ticket ที่แตะการประกอบ subprocess command หรือ parse daemon socket input จาก input ภายนอกโดยตรง; งานเสี่ยงต่ำใช้ lightweight review
- หากมีการแก้ไขหลังเข้า review ให้ปรับ `Review Notes` และรัน verification ใหม่ (pytest + manual run)
- ต้องใช้ `using-superpowers` ก่อนเริ่ม ticket และใช้ skill อื่นตามความเหมาะสมของ scope
- หาก ticket มี ambiguity หรือ plan risk ให้ย้อนกลับไป `/kanban plan`; หากมี bug report หรือ test/runtime/audio failure ที่ root cause ยังไม่ชัด ให้ใช้ `systematic-debugging`/`debugging-and-error-recovery`
- ถ้ามีไฟล์เปลี่ยนแปลงที่ไม่ได้เกี่ยวกับ ticket ห้าม revert เอง ให้ทำงานเฉพาะ scope ของ ticket
