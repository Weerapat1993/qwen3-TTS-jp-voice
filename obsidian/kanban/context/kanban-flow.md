# Kanban Ticket Flow

ใช้ไฟล์นี้เป็น workflow กลางเมื่อสั่ง AI ให้ทำ ticket ใน `obsidian/kanban/tasks/`

## Product-Level Reference

โปรเจกต์นี้ไม่มี `prd.md` กลาง ใช้ `README.md` (root) เป็นแหล่งอ้างอิงภาพรวมของ scope, CLI reference, daemon protocol/config และ troubleshooting; `README_HERMES.md` (root) เป็นแหล่งอ้างอิงของ Hermes CLI / MCP bridge integration ที่แยกจาก TTS core flow ไม่มี `AGENTS.md` ในโปรเจกต์นี้

ต้องอ่าน `README.md` เมื่อ ticket หรือคำสั่งเกี่ยวข้องกับ:

- เพิ่ม/แก้ CLI flag ใน `main.py` หรือ `qwen_clone_tts.py`
- แก้ daemon protocol, queue, cache, หรือ env var ใน `tts_daemon.py`
- เพิ่ม script entry point ใหม่ที่ผู้ใช้เรียกตรง (`tune_voice.py` เป็นต้น)
- แก้ behavior ที่กระทบ backward compatibility ระหว่าง `qwen_clone_tts.py` กับ daemon

ถ้า ticket หรือคำสั่งขัดกับพฤติกรรมเดิมใน `README.md` ให้เพิ่มหรืออัปเดต `### Open Questions` และถามผู้ใช้ว่าจะปรับ behavior/README หรือให้ถือเป็น exception เฉพาะงานนั้น ห้ามเดาเองว่า behavior เดิมหรือคำสั่งใหม่ถูกกว่า

## Board File

Board อยู่ในไฟล์เดียวที่ `obsidian/kanban/work-kanban-board.md` มี frontmatter `kanban-plugin: board` สำหรับให้ Obsidian render เป็น visual board และมี `## COLUMN` sections:

- `## BACKLOG` — ticket ที่ยังไม่เริ่ม
- `## PLAN` — ticket ที่กำลัง planning
- `## TODO` — ticket ที่ plan แล้วและพร้อมเริ่ม
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

Ticket file ต้องเป็น source of truth ของงานนั้นเสมอ ใช้ YAML frontmatter ตามตัวอย่างจริงใน `obsidian/kanban/tasks/TTS-1000.md`:

```md
---
ticket_id: TTS-XXXX
title: Ticket title
type: feature
status: todo
priority: high
tags:
  - kanban/ticket
  - work
---

## 🟢 TTS-XXXX: Ticket title

Status: Todo
Priority: High
Ref: <optional link to spec/GitHub issue>

### Summary
...

### Context
...

### Scope
...

### Acceptance Criteria
...

### Validation
...
```

กติกาสำคัญ:

- หนึ่ง ticket ต่อหนึ่งไฟล์เท่านั้น
- ชื่อไฟล์ต้องตรงกับ ticket id เช่น `obsidian/kanban/tasks/TTS-1001.md`
- `status:` ใน frontmatter และ `Status:` ใน body ต้องตรงกับ board ที่มี link ไปหา ticket นั้น
- ห้าม duplicate link ของ ticket เดียวกันไว้หลาย board พร้อมกัน
- ห้ามย้ายหรือ rename ticket file เมื่อเปลี่ยนสถานะ ให้ย้ายเฉพาะ link ระหว่าง board files

## Local Provider Commands

`kanban` skill อ้างถึงคำสั่งของ project ด้วย **operation name** กลาง ๆ เท่านั้น ตารางนี้คือ mapping ของ project นี้ (Qwen3-TTS Apple Silicon CLI/daemon — ไม่มี web framework, ไม่มี DB, ไม่มี Discord bot) แทนที่ `TTS-XXXX` ด้วย ticket id จริง

โปรเจกต์นี้ตั้ง `.kanban.json` ไว้เป็น `"provider": "notion"` อยู่แล้ว (มี `notionDataSourceId` และ `notionStatusMap` จริง) ดังนั้น `import-ticket`/`sync-ticket` ทำงานผ่าน Notion REST API (`ntn api ...`) โดยตรงตาม SKILL.md ของ kanban skill ไม่ต้องมี local command เพิ่มเติม

| Operation | Command |
|---|---|
| `import-ticket` | จัดการผ่าน notion provider ตาม `.kanban.json` (ดู SKILL.md `Configuration` section) — ไม่มี local command เพิ่มเติม |
| `sync-ticket` | เช่นเดียวกับ `import-ticket` |
| `create-pr` | `gh pr create` (ดู skill `git-workflow-and-versioning` สำหรับ flow มาตรฐาน) |
| `sync-progress` | N/A — โปรเจกต์นี้ไม่มี dashboard/progress bar widget ที่ต้อง sync ให้ข้ามขั้นตอนนี้เงียบ ๆ |
| `lark-create` | N/A — ยังไม่มี `lark-cli` หรือ Lark task config ผูกกับ repo นี้ |
| `lark-rename` | N/A เช่นเดียวกัน |
| `lark-move` | N/A เช่นเดียวกัน |
| `lark-help` | ใช้ `lark-cli --help` ตรง ๆ ถ้าผู้ใช้ติดตั้งไว้ระดับเครื่อง |

Lark task config: โปรเจกต์นี้ไม่มี environment variable สำหรับ Lark tasklist ผูกไว้ ถ้าผู้ใช้ต้องการเปิดใช้ optional Lark sync ต้อง setup `lark-cli` และ tasklist config เองก่อน

### post-implementation

หลัง implement เสร็จใน `/kanban start` ให้ทำตามลำดับนี้ก่อนรัน validation ของ ticket:

1. โปรเจกต์นี้ไม่มี database/model และไม่มี migration tool ใด ๆ — ข้ามขั้นตอน schema/seeder เสมอ
2. ถ้า ticket เพิ่มหรือเปลี่ยน environment variable ใหม่ที่ `tts_daemon.py`/สคริปต์อื่นอ่าน ให้อัปเดตตาราง env var ใน `README.md` คู่กับโค้ดเสมอ (โปรเจกต์นี้ไม่มี `.env.example` แยก มี `.env` จริงเท่านั้น — อย่า commit ค่า secret ใด ๆ ถ้าเพิ่มเข้าไป)
3. ถ้า ticket แก้ daemon protocol (request/response JSON schema) ให้ตรวจว่า `qwen_clone_tts.py` client ยัง parse response เดิมได้ (backward compatible) ก่อนถือว่า implement เสร็จ

### Deployment Report

ตอน report ผลของ `/kanban start` ต้องบอกสิ่งที่ผู้ใช้ต้องทำเมื่อใช้งานจริง (deploy ในที่นี้คือรันบนเครื่อง Apple Silicon ของผู้ใช้เอง ไม่ใช่ deploy ขึ้น server):

- ระบุถ้ามี environment variable ใหม่ที่ต้องตั้งก่อนรัน daemon/CLI (นอกเหนือจาก default ใน README.md)
- ระบุถ้ามี dependency ใหม่ที่ต้องเพิ่มใน `requirements.txt` และติดตั้งใหม่ (`pip install -r requirements.txt` ใน `.venv`)
- ระบุถ้าต้อง restart daemon ที่รันอยู่ (`tts_daemon.py`) เพื่อให้ code เปลี่ยนมีผล หรือต้องแก้/reinstall `launchd/com.liino.qwen-tts-daemon.plist`
- ระบุชัดเจนเมื่อไม่ต้องทำอะไรเลยนอกจาก pull โค้ดใหม่

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

## Flow

### 1. Create Ticket

เมื่อสร้าง ticket ใหม่:

1. ใช้ `using-superpowers` เพื่อเลือก skill ที่เหมาะกับ ticket นี้
2. อ่าน `README.md` (และ `README_HERMES.md` ถ้าเกี่ยวกับ Hermes/MCP bridge) ถ้างานแตะ CLI flag, daemon protocol, หรือ env var; ข้ามได้ถ้าเป็นงาน copy-only/board-only
3. ใช้ `brainstorming` ถ้า requirement ยังไม่ชัด, มีหลายแนวทาง, ต้องแตก scope, หรือชนกับ behavior เดิม
4. สร้าง `obsidian/kanban/tasks/TTS-XXXX.md` พร้อม frontmatter (`ticket_id`, `title`, `type`, `status: backlog`, `priority`, `tags`), `Status: Backlog`, priority, summary, context, scope, acceptance criteria, และ validation
5. เพิ่ม link ของ ticket ใน `obsidian/kanban/work-kanban-board.md (## BACKLOG)`
6. ถ้า optional Lark sync เปิดอยู่ ให้แจ้งผู้ใช้ว่าต้อง backfill ผ่าน `lark-cli` เอง (ไม่มี local command อัตโนมัติ)

ห้ามสร้าง ticket เป็น block ยาวใน `obsidian/kanban/work-kanban-board.md (## BACKLOG)`

### 2. Start Ticket

เมื่อผู้ใช้สั่งให้เริ่มทำ ticket:

1. หา link ของ ticket จาก board file ปัจจุบัน โดยปกติคือ `obsidian/kanban/work-kanban-board.md (## PLAN)`, `(## BACKLOG)` หรือ `(## TODO)`
2. อ่าน ticket file จาก `obsidian/kanban/tasks/TTS-XXXX.md`
3. อ่าน `README.md`/`README_HERMES.md` เมื่อ ticket เข้าเงื่อนไข Product-Level Reference ด้านบน
4. อ่าน context, related script(s) (`main.py`/`qwen_clone_tts.py`/`tts_daemon.py`/`tune_voice.py`) และ acceptance criteria ที่ ticket อ้างถึง
5. ถ้า ticket ขัดกับ behavior เดิมใน `README.md` และผู้ใช้ยังไม่ approve exception ให้เพิ่มหรืออัปเดต `### Open Questions` และหยุดก่อนย้ายเข้า `In Progress`
6. ถ้า ticket มี `### Implementation Plan` และ `Status: Plan` แล้ว ให้เริ่มต่อได้ทันทีโดยไม่เรียก `writing-plans` ซ้ำ
7. ถ้า ticket อยู่ `Status: Backlog` สามารถข้าม `Plan` และย้ายเข้า `In Progress` ได้ทันทีเมื่อครบทุกเงื่อนไขนี้:
   - acceptance criteria ชัดเจน
   - context ที่จำเป็นมีครบ หรือไม่จำเป็นต่อการตัดสินใจ
   - ไม่มี `### Open Questions` หรือ blocking notes ที่ยังไม่ resolved
   - งานเล็ก ความเสี่ยงต่ำ และไม่เข้าเกณฑ์ที่ควรใช้ `writing-plans` ตาม Plan Ticket flow
8. ถ้า backlog ticket ไม่ครบทุกเงื่อนไขสำหรับการข้าม `Plan` ให้ทำ Plan Ticket flow ก่อน และหยุดถ้า plan ทำให้เกิด `Open Questions`
9. ใช้ skill `using-superpowers` เพื่อเลือก skill ที่เหมาะกับงานก่อนเริ่ม implement
10. ย้ายเฉพาะ link ของ ticket ไป `obsidian/kanban/work-kanban-board.md (## INPROGRESS)`
11. เปลี่ยน `Status:`/`status:` ใน ticket file เป็น `In Progress`/`inprogress`
12. ทำงานตาม scope และ acceptance criteria
13. หลัง implement และ validation ให้ report ผลงานและบอกว่า ticket พร้อม review หรือยัง
14. ห้ามย้าย ticket ไป `Review` อัตโนมัติระหว่างคำสั่ง `start` แม้ implementation และ validation จะผ่านแล้ว
15. ต้องรอคำสั่ง `/kanban move-review TTS-XXXX` แบบ explicit ก่อน จึงค่อยเพิ่ม `Review Notes`, ย้าย board link ไป `(## REVIEW)`, และเปลี่ยน `Status:` เป็น `Review`

ห้ามเริ่ม implement หาก ticket ไม่มี acceptance criteria หรือ context ที่จำเป็นต่อการตัดสินใจ

### 2A. Plan Ticket

เมื่อผู้ใช้สั่งให้ plan ticket ก่อนเริ่มงาน:

1. หา ticket file จาก `obsidian/kanban/tasks/TTS-XXXX.md` และอ่าน context/AC/validation ที่จำเป็น
2. อ่าน `README.md`/`README_HERMES.md` เมื่อ ticket เข้าเงื่อนไข Product-Level Reference ด้านบน
3. ใช้ skill `using-superpowers` เพื่อเลือก skill ที่เหมาะกับการวางแผน
4. แสดง pre-plan assessment สั้น ๆ: status/board ปัจจุบัน, ควรใช้ `brainstorming` หรือไม่, ควรใช้ `writing-plans` หรือไม่, behavior alignment กับ `README.md`, และไฟล์/สถานะที่จะเปลี่ยน
5. ถามผู้ใช้ด้วย `Yes` / `No` ว่าจะ plan ต่อหรือไม่; ถ้า `No` ให้หยุด
6. ถ้า context ยังไม่พอ หรือ ticket ขัดกับ behavior เดิมและยังไม่ได้รับ approval ให้เพิ่ม `### Open Questions` แล้วหยุด
7. ถ้า `brainstorming` ถูกแนะนำ ให้ใช้เพื่อ clear scope / approach / decision ที่สำคัญ (เช่น เปลี่ยน cache key, protocol field, หรือ default env var); ถ้าทำให้ยังตอบไม่ได้ ให้หยุดและบันทึก `Open Questions`
8. ถ้า `writing-plans` ถูกแนะนำ ให้ใช้หลัง `brainstorming` resolved แล้ว; ถ้าไม่ถูกแนะนำ ให้เขียน plan แบบ concise ได้เลย
9. เพิ่มหรืออัปเดต `### Implementation Plan` โดยใส่ context, planned changes, files likely to change, validation commands (manual CLI/daemon run — ไม่มี automated test suite), และ risks / decisions
10. ย้ายเฉพาะ link ของ ticket ไป `obsidian/kanban/work-kanban-board.md (## PLAN)` และเปลี่ยน `Status:` เป็น `Plan`
11. ห้าม implement code changes ระหว่างคำสั่ง plan

แนะนำ `brainstorming` เมื่อ requirement ยังไม่ชัด, มีหลาย approach, มี `Open Questions`, ต้องแตก scope, มี tension กับ behavior เดิมใน README.md, หรือมี decision สำคัญที่ไม่ควรเดาระหว่าง implementation (เช่น breaking daemon protocol)

แนะนำ `writing-plans` เมื่อ ticket แตะหลายไฟล์ หลาย script (CLI + daemon), daemon protocol/cache, หรือมี regression risk ชัดเจน; งาน copy-only, board-only, documentation-only, หรือ single-file low-risk ใช้ plan แบบ concise ได้

เมื่อผู้ใช้สั่ง `start`:

1. ถ้ามี `### Implementation Plan` และ `Status: Plan` แล้ว ให้ดำเนิน Start Ticket ต่อ
2. ถ้าอยู่ `Backlog` และครบเงื่อนไขข้าม `Plan` ให้ย้ายเข้า `In Progress` ได้เลย
3. ถ้ายังไม่มี plan หรือ plan ยังมี `Open Questions` ให้กลับมาทำ Plan Ticket ก่อน

### 3. Superpowers Gate

ใช้ skill เหล่านี้เป็น workflow helper ระหว่างทำ ticket โดยไม่แทนที่ `README.md` หรือ review gates ของ repo นี้

Skill map:

- `using-superpowers`: ขั้นแรกของทุก ticket
- `brainstorming`: requirement ยังคลุมเครือ, ต้องเลือก approach, หรือแตกงานจาก scope ใหญ่เกินไป
- `writing-plans`: `/kanban plan` เมื่อ pre-plan assessment แนะนำ
- `systematic-debugging` / `debugging-and-error-recovery`: bug/debug gate สำหรับ repro, trace, isolate root cause เมื่อ manual validation fail, bug ยังไม่ชัด, behavior ไม่ตรง AC, หรือเจอ runtime error (เช่น daemon crash, model load fail)
- `code-review`: outsider review gate สำหรับ plan/diff/code change ที่มี regression risk หรือแตะ daemon protocol
- `security-review`: เพิ่มเติมจาก `code-review` เมื่อ ticket แตะ subprocess/ffmpeg invocation หรือ daemon socket input parsing

เกณฑ์ขั้นต่ำ:

- Ticket เล็กและชัดเจน: ใช้ `using-superpowers` อย่างน้อยหนึ่งครั้งก่อนเริ่ม
- Ticket ที่ไม่ชัด: ใช้ `brainstorming` ก่อน finalize scope, AC หรือ `### Implementation Plan`
- Ticket เสี่ยงหรือ context ไม่พอ: ผ่าน `/kanban plan` ก่อน `/kanban start`
- Bug report / regression / runtime fail (daemon crash, model load error, ffmpeg fail): ใช้ `systematic-debugging` หรือ `debugging-and-error-recovery` ก่อนเสนอ fix
- Plan/diff/code change เสี่ยงหรือหลาย script: ใช้ `code-review`
- Ticket ที่แตะ subprocess/ffmpeg หรือ socket input parsing: เพิ่ม `security-review`

ถ้าใช้ skill เหล่านี้ระหว่าง ticket ให้บันทึกสั้น ๆ ใน `Review Notes` หรือ `Done Notes` ว่าใช้ skill ใดและช่วยตัดสินใจเรื่องอะไร

### 4. Implementation Gate

ระหว่างทำ ticket ต้องปฏิบัติตาม:

- `README.md` / `README_HERMES.md` (ตามที่เกี่ยวข้อง)
- `obsidian/kanban/context/requirements.md`
- `obsidian/kanban/context/coding-style.md`
- Existing project conventions (argparse CLI pattern, env-var-only daemon config, stdout/stderr result reporting)

ทุก code change ต้อง validate ด้วยการรันจริง (ไม่มี automated test suite ในโปรเจกต์นี้) เช่น:

- รัน `python qwen_clone_tts.py --text "..." --out outputs/<file>.wav` แล้วตรวจ `OK <path>` + ฟังไฟล์จริง
- ถ้าแก้ daemon: start daemon ใหม่, ยิง request ผ่าน client จริง, ตรวจ response JSON และ telemetry log
- ถ้า ticket เพิ่ม pure logic ที่ควรมี automated test (parsing, cache key, queue timeout) ให้พิจารณาเพิ่ม `tests/` + `pytest` ตามที่ระบุใน `coding-style.md` และบันทึกการตัดสินใจนี้ใน plan

หาก manual validation fail และสาเหตุยังไม่ชัด ให้ใช้ skill `systematic-debugging` เพื่อแยก root cause ก่อนแก้ไข

หากเป็น bug report, regression, หรือ behavior ที่ผู้ใช้แจ้งว่า "เสีย", "ไม่ทำงาน", "เสียงผิด", "error", "crash", "failing" ให้ใช้ skill `debugging-and-error-recovery` หรือ `systematic-debugging` ตั้งแต่เริ่ม debug เว้นแต่ผู้ใช้บอกให้ข้าม แต่ยังต้องทำตามขั้นตอน repro → trace → falsify ภายในงานนั้น

### 5. Move To Review

เมื่อ implementation ผ่าน:

1. เพิ่ม `Review Notes` แบบสั้นใน ticket file
2. ย้าย link จาก `obsidian/kanban/work-kanban-board.md (## INPROGRESS)` ไป `(## REVIEW)`
3. เปลี่ยน `Status:`/`status:` เป็น `Review`/`review`

ตัวอย่าง `Review Notes`:

```md
### Review Notes
- Files: `qwen_clone_tts.py`, `tts_daemon.py`
- Commands: manual run `python qwen_clone_tts.py --text "..." --out outputs/test.wav` (OK), daemon round trip ผ่าน
- Skills: `using-superpowers`, `writing-plans`
```

### 6. Review Gate

หลัง ticket อยู่ใน `obsidian/kanban/work-kanban-board.md (## REVIEW)`:

- ใช้ `code-review` ถ้างานมี plan, หลาย script/หลาย layer (CLI + daemon), regression risk, หรือผู้ใช้ขอ review โดยตรง
- ใช้ `security-review` เพิ่มเมื่อแตะ subprocess/ffmpeg invocation หรือ daemon socket input parsing
- งานเล็กและ low-risk ใช้ lightweight review โดยเช็ก AC, scope, manual validation, และไม่มี obvious regression

ให้ผลลัพธ์เป็น:

```md
Review type: Lightweight / code-review / security-review
Verdict: PASS / NEEDS FIX / BLOCKED

Findings:
- ...

Missing manual validation:
- ...

Commands run:
- ...

Move to done: Yes / No
```

ถ้า `NEEDS FIX`:

1. แก้ issue ทันที
2. รัน manual validation ที่เกี่ยวข้องอีกครั้ง
3. ใช้ `systematic-debugging` หรือ `debugging-and-error-recovery` เมื่อ root cause ยังไม่ชัด
4. Review ซ้ำด้วย gate เดิม หรืออัปเกรดเป็น `security-review` หาก fix ทำให้งานมี security impact
5. ห้ามย้ายไป done จนกว่า verdict เป็น `PASS`

ถ้า `BLOCKED`:

1. เก็บ link ของ ticket ไว้ใน `(## REVIEW)`
2. เพิ่ม `Blocked Notes` ใน ticket file
3. ระบุสิ่งที่ต้องการจากผู้ใช้หรือ dependency ที่ขาด (เช่น ต้องมี hardware Apple Silicon จริงเพื่อ verify GPU/Metal behavior)

### 7. Move To Done

เมื่อ Review Gate ให้ verdict `PASS`:

1. เพิ่ม `Done Notes` แบบสั้นใน ticket file (รวม root cause ถ้าเป็น bugfix — โปรเจกต์นี้ไม่มี skill `post-mortem` แยก ให้บันทึกสั้น ๆ ตรงนี้แทน)
2. ย้าย link จาก `(## REVIEW)` ไป `(## DONE)`
3. เปลี่ยน `Status:`/`status:` เป็น `Done`/`done`
4. ถ้า optional Lark sync เปิดอยู่ ให้แจ้งผู้ใช้ backfill ผ่าน `lark-cli` เอง (ไม่มี local command อัตโนมัติ)

ตัวอย่าง `Done Notes`:

```md
### Done Notes
- Review Gate: PASS
- Gates passed: lightweight review, manual CLI/daemon validation
- Validation: manual run ผ่าน (`OK outputs/test.wav`)
- Root cause (ถ้าเป็น bugfix): ...
```

### 8. Close Or Archive Ticket

ใช้ `obsidian/kanban/work-kanban-board.md (## CLOSED)` เฉพาะ ticket ที่ยกเลิกหรือไม่ต้องทำต่อ

เมื่อ close ticket:

1. เพิ่ม `Closed Notes` ใน ticket file
2. ย้ายเฉพาะ link ของ ticket จาก board ปัจจุบันไป `(## CLOSED)`
3. เปลี่ยน `Status:`/`status:` ใน ticket file เป็น `Closed`/`closed`
4. ระบุเหตุผลที่ปิด เช่น duplicate, obsolete, out of scope, หรือ replaced by ticket อื่น

### 9. Close Sprint

เมื่อผู้ใช้สั่ง `/kanban sprint close` หรือ `/kanban sprint close --name=splint-X`:

1. อ่าน `obsidian/kanban/work-kanban-board.md` และรวบรวม entries ทั้งหมดใน `## DONE` และ `## CLOSED`
2. ถ้าทั้งสอง section ว่างเปล่า ให้ report ว่าไม่มีอะไร archive และหยุด
3. กำหนดชื่อ splint file ใหม่:
   - ถ้ามี `--name=` ให้ใช้ค่านั้น (เช่น `splint-3`)
   - ถ้าไม่มี ให้ scan ไฟล์ `obsidian/kanban/splint-*.md` ที่มีอยู่ หาเลขสูงสุด แล้ว +1
4. สร้าง `obsidian/kanban/splint-N-kanban-board.md` ด้วย format ที่มีเฉพาะ `## DONE` และ `## CLOSED` sections พร้อม links จากข้อ 1
5. ลบ entries ของ tickets ที่ archive แล้วออกจาก `## DONE` และ `## CLOSED` ใน `work-kanban-board.md`
6. ห้ามแตะ sections อื่น (`## BACKLOG`, `## PLAN`, `## TODO`, `## INPROGRESS`, `## REVIEW`) — tickets ที่ยังค้างอยู่ที่เดิมโดยอัตโนมัติ
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
- ห้ามย้าย ticket ไป done หาก review verdict ไม่ใช่ `PASS` หรือยังขาด manual validation ที่จำเป็น
- ใช้ `security-review` เฉพาะ ticket ที่แตะ subprocess/ffmpeg invocation หรือ daemon socket input parsing; งานเสี่ยงต่ำใช้ lightweight review
- หากมีการแก้ไขหลังเข้า review ให้ปรับ `Review Notes` และรัน verification ใหม่
- ต้องใช้ `using-superpowers` ก่อนเริ่ม ticket และใช้ skill อื่นตามความเหมาะสมของ scope
- หาก ticket มี ambiguity หรือ plan risk ให้ย้อนกลับไป `/kanban plan`; หากมี bug report หรือ runtime failure ที่ root cause ยังไม่ชัด ให้ใช้ `systematic-debugging`/`debugging-and-error-recovery`
- ถ้ามีไฟล์เปลี่ยนแปลงที่ไม่ได้เกี่ยวกับ ticket ห้าม revert เอง ให้ทำงานเฉพาะ scope ของ ticket
