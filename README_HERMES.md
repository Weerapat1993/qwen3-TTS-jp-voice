# Prompt: บริบทการทำงาน Qwen3-TTS ฝั่ง Hermes

> ไฟล์นี้เป็น prompt สำหรับ AI agent (เช่น Hermes) ให้อ่านเพื่อเข้าใจว่าระบบ
> Qwen3-TTS เชื่อมกับ Hermes อย่างไร และเวลาแก้ไข/เพิ่มฟีเจอร์ต้องทำอะไรบ้าง

---

## 1. ภาพรวมระบบ

Hermes Agent บนเครื่องนี้ใช้ TTS provider แบบ **command provider** ชื่อ
`liino-clone` ซึ่งเรียกสคริปต์ Python ในโปรเจกต์ Qwen3-TTS เพื่อสังเคราะห์เสียง
พูดด้วยเสียงโคลน "Liino" ทั้งหมดรัน local บน Apple Silicon (MLX) ไม่ใช้ cloud

```
Hermes (text_to_speech tool)
   └─ command provider "liino-clone"  (ประกาศใน config.yaml ฝั่ง tts.providers)
        └─ เรียก: qwen_clone_tts.py --stdin <input.txt> <output.wav>
             └─ เชื่อมต่อ tts_daemon.py (Unix socket /tmp/qwen_tts_daemon.sock)
                  └─ โมเดล: models/Qwen3-TTS-12Hz-1.7B-Base-8bit (MLX)
                       └─ เสียงอ้างอิง: voices/<Name>.wav  (voice cloning)
```

### ไฟล์สำคัญ

| Path | หน้าที่ |
|---|---|
| `/Users/mungmee/Desktop/Project/Python/qwen3-tts-apple-silicon/` | โปรเจกต์ TTS หลัก |
| `qwen_clone_tts.py` | CLI สร้างเสียง; โหมด `--stdin <in> <out>` ใช้กับ Hermes; แบ่งข้อความเป็น chunk ≤300 ตัวอักษรแล้วต่อเสียง; `--lang <code>` optional (default `auto`, Hermes ไม่ต้องส่ง) |
| `tts_daemon.py` | daemon โหลดโมเดลค้างไว้ (socket `/tmp/qwen_tts_daemon.sock`) ลดเวลาโหลดโมเดลซ้ำ |
| `voices/*.wav` | เสียงต้นฉบับสำหรับโคลน เช่น `Liino.wav` |
| `voice-intro/*.wav` | เสียงแนะนำตัวตอนเข้า Voice Channel (`Liino_Intro.wav`) — แยกจาก voices/ กัน voice-clone ทับ |
| `models/` | โมเดล MLX 8-bit |
| `~/.hermes/skills/creative/tts-voice-clone/SKILL.md` | skill ของ Hermes ที่สรุปวิธีใช้ + pitfalls |

### ข้อกำหนดที่ต้องจำ (สำคัญมาก)

- **ใช้ Python ของ venv โปรเจกต์เท่านั้น**: `.venv/bin/python` (Python 3.13)
  - ห้ามใช้ `python3` ระบบ (3.9) — สคริปต์ใช้ syntax `str | None` ที่ต้องใช้ Python ≥3.10
  - อาการเมื่อใช้ผิด: provider รายงาน `TTS chunk 1 produced no final audio`
- **ส่งข้อความผ่านไฟล์** (`--stdin input.txt`) ห้าม pipe ผ่าน `echo | python`
- ความเร็ว: ~15–17 วินาที/ประโยคสั้น, memory peak ~6.7GB, RTF 0.57x
- ผลลัพธ์เป็นไฟล์ `.wav` 24kHz mono Int16

---

## 2. การตั้งค่าฝั่ง Hermes

### 2.1 TTS provider (config.yaml ของ profile)

```yaml
tts:
  provider: liino-clone          # default provider
  providers:
    liino-clone:
      command: /Users/mungmee/Desktop/Project/Python/qwen3-tts-apple-silicon/.venv/bin/python
      args: [/Users/mungmee/Desktop/Project/Python/qwen3-tts-apple-silicon/qwen_clone_tts.py, --stdin]
      # รูปแบบการเรียก: <command> <args...> <input.txt> <output.wav>
      truncate: 300
```

*หมายเหตุ: ถ้า provider นี้ fail ให้ fallback เป็น provider `edge` (ฟรี แต่ไม่ใช่เสียงโคลน)
และแจ้งผู้ใช้ว่าเสียงไม่ใช่เสียง Liino*

### 2.2 Discord voice_fx (config.yaml)

```yaml
discord:
  voice_fx:
    enabled: true
    intro_path: /Users/mungmee/Desktop/Project/Python/qwen3-tts-apple-silicon/voice-intro/Liino_Intro.wav
    # ambient_enabled, ambient_gain, duck_gain, speech_gain, lead_silence_ms, ack_* มี default อยู่แล้ว
```

---

## 3. ฟีเจอร์ที่เพิ่มเอง (สิ่งที่ต้องทำเพิ่มนอกเหนือจากต้น Hermes)

### 3.1 Liino_Intro — เสียงแนะนำตัวเมื่อเข้า Voice Channel

**ที่มา:** ต้น Hermes ไม่มี on-join greeting จึงแก้โค้ดเอง 1 จุด + ตั้งค่า config

**การแก้โค้ด** ใน `~/.hermes/hermes-agent/plugins/platforms/discord/adapter.py`:

1. เพิ่ม default key ใน `_load_voice_fx_config()` (ประมาณบรรทัด 4322):
   ```python
   "intro_path": "",   # audio file played once when the bot joins a voice channel
   ```
2. ใน `join_voice_channel()` (ประมาณบรรทัด 4607) ก่อน `return True` สุดท้าย
   (หลังบล็อก `_install_voice_mixer`) เพิ่ม:
   ```python
   # Intro greeting: play a configured audio file once after joining.
   intro_path = str(getattr(self, "_voice_fx_cfg", {}).get("intro_path", "") or "")
   if intro_path and os.path.isfile(intro_path):
       async def _play_intro(_guild_id, _vc, _path):
           try:
               await asyncio.sleep(0.5)          # รอ voice socket settle
               cur = self._voice_clients.get(_guild_id)
               if cur is None or cur is not _vc or not cur.is_connected():
                   return
               await self.play_in_voice_channel(_guild_id, _path)
           except Exception as e:
               logger.warning("Voice intro playback failed: %s", e)
       asyncio.ensure_future(_play_intro(guild_id, vc, intro_path))
   elif intro_path:
       logger.warning("Voice intro file not found: %s", intro_path)
   ```
   **เหตุผลการออกแบบ:**
   - spawn เป็น task แยก → join ไม่ถูก block และ intro ล้มเหลวไม่กระทบการ join
   - เช็ค `cur is _vc` กัน race: ถ้าบอทย้ายห้อง/ออกก่อน intro เล่น จะยกเลิกเอง
   - ใช้ `play_in_voice_channel()` เดิม ซึ่งรองรับทั้ง mixer path (duck ambient)
     และ legacy FFmpegPCMAudio path อยู่แล้ว

**การตั้งค่า** (ทำครั้งเดียว):
```bash
hermes config set discord.voice_fx.enabled true --force
hermes config set discord.voice_fx.intro_path <absolute path ของ .wav> --force
```
*ใช้ `--force` เพราะเป็น key ที่ต้น Hermes ยังไม่รู้จัก*

**การรีสตาร์ท:** โค้ด adapter โหลดตอน gateway start จึงต้อง restart:
```bash
hermes gateway restart        # รันจาก shell ปกติเท่านั้น
```
⚠️ ถ้ารันคำสั่งนี้จาก "ภายใน" agent ที่ทำงานอยู่บน gateway ตัวเดียวกัน คำสั่งจะถูกบล็อก
(ต้องให้ผู้ใช้รันเอง หรือรันจาก shell ภายนอก)

### 3.2 สร้างไฟล์เสียงใหม่ (เช่น intro, เสียงโคลนใหม่)

```bash
cd /Users/mungmee/Desktop/Project/Python/qwen3-tts-apple-silicon
printf '<ข้อความ>' > /tmp/tts_text.txt
.venv/bin/python qwen_clone_tts.py --stdin /tmp/tts_text.txt <output.wav>
# ระบุภาษา (ไม่บังคับ — default auto): --lang japanese
# โหมด CLI เต็ม: --text "..." --voice <Name> --out <file.wav> --instruct "บรรยายน้ำเสียง"
```

เสียงโคลนใหม่: วางไฟล์ตัวอย่าง 5–10 วินาทีเป็น `voices/<Name>.wav` แล้วใช้ `--voice <Name>`

---

## 4. Checklist เมื่อแก้ไข/เพิ่มฟีเจอร์ที่เกี่ยวกับระบบนี้

1. แก้โค้ดใน `~/.hermes/hermes-agent/` → ตรวจ syntax ด้วย venv ของ hermes:
   `/Users/mungmee/.hermes/hermes-agent/venv/bin/python -c "import ast; ast.parse(open('<file>').read())"`
2. ตั้งค่าใหม่ → `hermes config set <key> <value> --force` (ห้ามแก้ config.yaml มือเปล่า)
3. รีสตาร์ท gateway จาก shell ภายนอก → `hermes gateway restart`
4. ทดสอบจริง: ใช้ `/voice join` ใน Discord แล้วยืนยันว่าเสียง intro เล่น, ดู log ที่ `~/.hermes/logs/gateway.log`
5. อัปเดต skill `tts-voice-clone` ถ้าพบ pitfall ใหม่

---

## 5. สรุป "ต้องทำอะไรเพิ่ม" เมื่อย้ายเครื่อง / ติดตั้งใหม่

- [ ] Install โปรเจกต์ TTS + venv (Python ≥3.10) + `brew install ffmpeg opus`
- [ ] Download โมเดล MLX จาก HuggingFace ไปไว้ที่ `models/`
- [ ] เตรียมไฟล์เสียงใน `voices/` (Liino.wav, Liino_Intro.wav)
- [ ] ประกาศ command provider `liino-clone` ใน `config.yaml` (tts section)
- [ ] ตั้ง `discord.voice_fx.enabled` + `intro_path`
- [ ] แพตช์ `adapter.py` ตามข้อ 3.1 (ต้น Hermes ยังไม่มีฟีเจอร์ intro ในตัว)
- [ ] `hermes gateway restart` แล้วทดสอบ `/voice join`
