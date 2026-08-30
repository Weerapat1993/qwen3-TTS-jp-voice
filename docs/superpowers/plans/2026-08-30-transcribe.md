# `/transcribe` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/transcribe file:<audio>` Discord slash command that turns an uploaded `.mp3`/`.wav` into emoji-mood-tagged text, ready to paste into `/say file:`.

**Architecture:** Local Whisper STT via `mlx-whisper` (no cloud), split into a pure-logic mood module and a thin STT wrapper, with the Discord command as glue in `discord_say_bot.py`. Output is text only — a `.txt` attachment plus an inline preview when short. No voice-channel playback, no TTS-daemon involvement.

**Tech Stack:** Python 3.10+, `discord.py` 2.7.1 (`app_commands`), `mlx-whisper` (Apple Silicon), `ffmpeg`/`ffprobe`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-30-transcribe-design.md`
**Ticket:** `obsidian/kanban/tasks/TTS-1005.md`

## Global Constraints

- Python 3.10+ syntax (`str | None` used). **Always run with `.venv/bin/python`**, never system `python3`.
- Comments and docstrings in Thai; code identifiers and error/log/user-facing strings follow existing file style (Thai user-facing strings in `discord_say_bot.py`, English in log lines).
- Pure-logic modules (`transcribe_mood.py`) must not `import discord`, `qwen_clone_tts`, or `mlx*` — mirrors `say_moods.py` so unit tests stay fast and side-effect-free.
- No new Discord intent. `intents = discord.Intents.default()` stays unchanged.
- Pin every new dependency in `requirements.txt` with `==` like existing lines.
- Tests live at repo root as `test_<module>.py`, run with `.venv/bin/python -m pytest` from the repo root.
- New env var default value, verbatim: `TRANSCRIBE_WHISPER_MODEL` → `mlx-community/whisper-large-v3-turbo`.
- Limits, verbatim: attachment ≤ `20 * 1024 * 1024` bytes; audio duration ≤ `600` seconds; inline-preview threshold `1800` characters.
- Accepted upload extensions: `.mp3`, `.wav` only.
- Errors and usage hints → ephemeral. Success → normal channel message.
- Commit messages use the `feat(TTS-1005): ` / `test(TTS-1005): ` / `docs(TTS-1005): ` prefix and end with the trailer:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
  ```
- Branch: `feature/TTS-1005` (already checked out).

---

### Task 1: `MOOD_EMOJI` reverse map in `say_moods.py`

**Files:**
- Modify: `say_moods.py` (add `MOOD_EMOJI` after the `EMOJI_MOOD` dict, ~line 22)
- Test: `test_say_moods.py` (add import + 3 tests)

**Interfaces:**
- Consumes: existing `say_moods.EMOJI_MOOD`, `say_moods.extract_mood`, `qwen_clone_tts.MOOD_PRESETS`
- Produces: `say_moods.MOOD_EMOJI: dict[str, str]` — mood name → one canonical emoji string. Keys are exactly `set(EMOJI_MOOD.values())`; every `MOOD_EMOJI[m]` is a key in `EMOJI_MOOD` that maps back to `m`. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

In `test_say_moods.py`, change the import block to add `MOOD_EMOJI`:

```python
from say_moods import (
    EMOJI_MOOD,
    MOOD_EMOJI,
    extract_mood,
    first_line_over_limit,
    parse_lines,
)
```

Append these tests to the end of the file:

```python
# --- MOOD_EMOJI (TTS-1005: reverse map for /transcribe line prefixes) ---

def test_mood_emoji_round_trips_through_extract_mood():
    for mood, emoji in MOOD_EMOJI.items():
        assert extract_mood(f"{emoji} ข้อความ") == ("ข้อความ", mood)


def test_mood_emoji_keys_are_real_presets():
    for mood in MOOD_EMOJI:
        assert mood in MOOD_PRESETS


def test_mood_emoji_covers_every_evocative_mood():
    assert set(MOOD_EMOJI) == set(EMOJI_MOOD.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_say_moods.py -q`
Expected: FAIL — `ImportError: cannot import name 'MOOD_EMOJI' from 'say_moods'`

- [ ] **Step 3: Add `MOOD_EMOJI` to `say_moods.py`**

Immediately after the closing `}` of the `EMOJI_MOOD` dict (currently line 22), add:

```python


# mood name -> emoji ตัวแทนหนึ่งตัวที่ extract_mood() map กลับมาเป็น mood เดิม
# เลือก emoji ตัวแรกของแต่ละกลุ่มใน EMOJI_MOOD ด้านบน; mood ที่ไม่มี emoji สื่อ
# ความหมายชัด (default, long) ตั้งใจไม่ใส่ -> /transcribe จะไม่เติม prefix
MOOD_EMOJI: dict[str, str] = {
    "excited": "😄",
    "giggle": "😆",
    "surprised": "😮",
    "sad": "😢",
    "angry": "😠",
    "sleepy": "😴",
    "whisper": "🤫",
    "gentle": "🥺",
    "bored": "😑",
    "storyteller": "📖",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_say_moods.py -q`
Expected: PASS — all tests (existing + 3 new) green.

- [ ] **Step 5: Commit**

```bash
git add say_moods.py test_say_moods.py
git commit -m "$(cat <<'EOF'
feat(TTS-1005): Add MOOD_EMOJI reverse map to say_moods

mood name -> canonical emoji, round-trips through extract_mood(). Used to
prefix /transcribe output lines so they paste back into /say file:.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 2: `transcribe_mood.py` — keyword → mood heuristic

**Files:**
- Create: `transcribe_mood.py`
- Test: `test_transcribe_mood.py`

**Interfaces:**
- Consumes: nothing at runtime; test imports `say_moods.MOOD_EMOJI` (from Task 1) to assert coverage.
- Produces:
  - `transcribe_mood.MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]]` — ordered; each entry is `(substrings, mood_name)`.
  - `transcribe_mood.detect_mood(text: str) -> str | None` — mood name of the first matching entry (case-insensitive substring), else `None`. Every returned mood is a key in `say_moods.MOOD_EMOJI`. Consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

Create `test_transcribe_mood.py`:

```python
"""Unit test สำหรับ transcribe_mood pure logic (TTS-1005)"""
from transcribe_mood import MOOD_KEYWORDS, detect_mood
from say_moods import MOOD_EMOJI


def test_detect_mood_thai_giggle():
    assert detect_mood("555 ขำมากเลยวันนี้") == "giggle"


def test_detect_mood_thai_sad():
    assert detect_mood("วันนี้เศร้าจังเลย ร้องไห้เลย") == "sad"


def test_detect_mood_english_angry():
    assert detect_mood("I am so furious right now") == "angry"


def test_detect_mood_case_insensitive():
    assert detect_mood("WOW that is unbelievable") == "surprised"


def test_detect_mood_no_keyword_returns_none():
    assert detect_mood("วันนี้อากาศดีนะ ไปเดินเล่นกัน") is None


def test_detect_mood_earlier_entry_wins():
    # "555" (giggle, entry 0) มาก่อน "เศร้า" (sad, entry 1)
    assert detect_mood("555 แต่ก็เศร้านะ") == "giggle"


def test_every_keyword_mood_has_canonical_emoji():
    for _needles, mood in MOOD_KEYWORDS:
        assert mood in MOOD_EMOJI, f"{mood!r} has no MOOD_EMOJI entry"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_transcribe_mood.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'transcribe_mood'`

- [ ] **Step 3: Create `transcribe_mood.py`**

```python
#!/usr/bin/env python3
"""Pure logic: เดา mood จากข้อความที่ถอดเสียงได้ (TTS-1005)

แยกจาก discord_say_bot.py / stt_transcribe.py เพื่อ unit test ได้ isolated —
ไม่ import discord, qwen_clone_tts หรือ mlx ใด ๆ (เหมือน say_moods.py)

detect_mood() คืนชื่อ mood ที่ say_moods.MOOD_EMOJI รู้จักเสมอ (หรือ None)
เพื่อให้เติม emoji canonical นำหน้าบรรทัดได้
"""

# ตารางเรียงตามลำดับความสำคัญ: entry แรกที่มี substring ใด ๆ อยู่ใน text ชนะ
# key = tuple ของ substring (ตัวพิมพ์เล็กแล้ว), value = ชื่อ mood ใน MOOD_EMOJI
MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("555", "ฮ่า", "ขำ", "ฮามาก", "lol", "haha", "lmao"), "giggle"),
    (("เศร้า", "เสียใจ", "ร้องไห้", "ผิดหวัง", "น้ำตา", "sad", "unhappy"), "sad"),
    (("โกรธ", "โมโห", "หงุดหงิด", "น่ารำคาญ", "angry", "furious"), "angry"),
    (("ตกใจ", "ว้าว", "ไม่น่าเชื่อ", "แปลกใจ", "wow", "omg", "whoa", "unbelievable"),
     "surprised"),
    (("ง่วง", "เหนื่อย", "อยากนอน", "เพลีย", "tired", "sleepy", "exhausted"),
     "sleepy"),
    (("กระซิบ", "เงียบ ๆ", "แอบบอก", "อย่าบอกใคร", "whisper", "secret"), "whisper"),
    (("ไม่เป็นไรนะ", "ใจเย็น ๆ", "กอดหน่อย", "เดี๋ยวก็ดีขึ้น", "there there",
      "it's okay"), "gentle"),
    (("เย้", "สุดยอด", "ตื่นเต้น", "ไปกันเลย", "เจ๋งมาก", "yay", "let's go",
      "awesome"), "excited"),
    (("เบื่อ", "น่าเบื่อ", "เฉย ๆ", "ไม่มีอะไรทำ", "bored", "boring", "meh"),
     "bored"),
    (("กาลครั้งหนึ่ง", "นานมาแล้ว", "ณ ดินแดน", "once upon a time", "long ago"),
     "storyteller"),
]


def detect_mood(text: str) -> str | None:
    """คืนชื่อ mood ของ entry แรกใน MOOD_KEYWORDS ที่มี substring ตรงกับ text

    เทียบแบบ case-insensitive (lower ทั้ง text; key ใน MOOD_KEYWORDS lower ไว้แล้ว)
    ไม่เจอเลย -> None
    """
    low = text.lower()
    for needles, mood in MOOD_KEYWORDS:
        if any(n in low for n in needles):
            return mood
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_transcribe_mood.py -q`
Expected: PASS — 7 tests green.

- [ ] **Step 5: Commit**

```bash
git add transcribe_mood.py test_transcribe_mood.py
git commit -m "$(cat <<'EOF'
feat(TTS-1005): Add transcribe_mood keyword heuristic

Ordered Thai+English substring table -> mood name (always a MOOD_EMOJI key).
Pure logic, no discord/mlx import, first-match-wins.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 3: `stt_transcribe.py` — Whisper wrapper + `requirements.txt`

**Files:**
- Create: `stt_transcribe.py`
- Modify: `requirements.txt` (add `mlx-whisper==0.4.3` after the `mlx-metal==0.30.3` line)
- Test: `test_stt_transcribe.py`

**Interfaces:**
- Consumes: `mlx_whisper` (new dep), `ffprobe` on `PATH`.
- Produces:
  - `stt_transcribe.WHISPER_MODEL: str` — `os.environ.get("TRANSCRIBE_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")`, read at import time.
  - `stt_transcribe.probe_duration(audio_path: str) -> float` — seconds via ffprobe; raises `RuntimeError` on any failure.
  - `stt_transcribe.transcribe(audio_path: str) -> list[str]` — stripped, non-empty Whisper segment texts in order. May raise (model load / decode). Both consumed by Task 4.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add a line directly below `mlx-metal==0.30.3`:

```
mlx-whisper==0.4.3
```

Then install it:

Run: `.venv/bin/python -m pip install mlx-whisper==0.4.3`
Expected: installs `mlx-whisper` and its deps, no error.

- [ ] **Step 2: Write the failing tests**

Create `test_stt_transcribe.py`:

```python
"""Unit test สำหรับ stt_transcribe (TTS-1005)

ครอบเฉพาะ config resolution + probe_duration; transcribe() ต้องมีโมเดล Whisper
จริง + ไฟล์เสียงจริง จึงทดสอบใน manual validation (ดู plan Task 4)
"""
import importlib
import shutil
import subprocess

import pytest

import stt_transcribe

_ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


@pytest.fixture(autouse=True)
def _restore_module():
    yield
    importlib.reload(stt_transcribe)


def test_whisper_model_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("TRANSCRIBE_WHISPER_MODEL", raising=False)
    reloaded = importlib.reload(stt_transcribe)
    assert reloaded.WHISPER_MODEL == "mlx-community/whisper-large-v3-turbo"


def test_whisper_model_env_override(monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_WHISPER_MODEL", "foo/bar-whisper")
    reloaded = importlib.reload(stt_transcribe)
    assert reloaded.WHISPER_MODEL == "foo/bar-whisper"


@pytest.mark.skipif(_ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_probe_duration_on_generated_wav(tmp_path):
    wav = tmp_path / "sine.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=3", str(wav)],
        check=True)
    assert 2.8 < stt_transcribe.probe_duration(str(wav)) < 3.2


def test_probe_duration_missing_file_raises():
    with pytest.raises(RuntimeError):
        stt_transcribe.probe_duration("/nonexistent/nope.wav")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_stt_transcribe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stt_transcribe'`

- [ ] **Step 4: Create `stt_transcribe.py`**

```python
#!/usr/bin/env python3
"""Whisper STT wrapper สำหรับ /transcribe (TTS-1005) — local, no cloud

ใช้ mlx-whisper บน Apple Silicon; ไม่ import discord
โมเดล default = mlx-community/whisper-large-v3-turbo (~1.6 GB, โหลดครั้งแรก
ลง Hugging Face cache) override ด้วย env var TRANSCRIBE_WHISPER_MODEL
ต้องมี ffmpeg/ffprobe ใน PATH (โปรเจกต์นี้ require อยู่แล้ว)
"""
import os
import subprocess

WHISPER_MODEL = os.environ.get(
    "TRANSCRIBE_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")


def probe_duration(audio_path: str) -> float:
    """คืนความยาวเสียง (วินาที) ผ่าน ffprobe

    raise RuntimeError ถ้า ffprobe ล้มเหลวหรือ parse ค่าไม่ได้
    (caller แปลงเป็น ephemeral error)
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", audio_path],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"ffprobe failed: {e}") from e
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()}")
    try:
        return float(out.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned no duration: {out.stdout!r}") from e


def transcribe(audio_path: str) -> list[str]:
    """ถอดเสียงไฟล์เป็น list ของข้อความต่อ segment (ตัด segment ว่างทิ้ง คงลำดับ)

    import mlx_whisper ในฟังก์ชัน เพื่อไม่ให้การ import โมดูลนี้ (เช่นตอน test
    probe_duration) ลาก mlx เข้ามาโหลดช้า
    mlx_whisper แคชน้ำหนักโมเดลเองใน HF cache — call แรกของโมเดลใหม่ = ดาวน์โหลด
    """
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio_path, path_or_hf_repo=WHISPER_MODEL, language="th")
    lines: list[str] = []
    for seg in result.get("segments", []):
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_stt_transcribe.py -q`
Expected: PASS — 4 tests green (or 3 pass + 1 skipped if ffmpeg absent, which it should not be).

- [ ] **Step 6: Commit**

```bash
git add stt_transcribe.py test_stt_transcribe.py requirements.txt
git commit -m "$(cat <<'EOF'
feat(TTS-1005): Add stt_transcribe Whisper wrapper

mlx-whisper local STT (default whisper-large-v3-turbo, TRANSCRIBE_WHISPER_MODEL
override) + ffprobe duration check. transcribe() returns per-segment lines.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 4: `/transcribe` slash command + README

**Files:**
- Modify: `discord_say_bot.py` (imports near line 29–43; new constants + `@tree.command` after the `say` function, before `def main()` ~line 315)
- Modify: `README.md` (env-var table + new `/transcribe` subsection under §Discord Bot; one line in the intro paragraph and the top features table)
- Test: none automated (Discord runtime path) — manual validation steps below

**Interfaces:**
- Consumes: `say_moods.MOOD_EMOJI` (Task 1), `transcribe_mood.detect_mood` (Task 2), `stt_transcribe.WHISPER_MODEL` / `probe_duration` / `transcribe` (Task 3), existing `qwen_clone_tts.MOOD_PRESETS`.
- Produces: registered application command `transcribe`.

- [ ] **Step 1: Add imports and constants**

In `discord_say_bot.py`, add `import io` to the stdlib import block (after `import asyncio`, keep alphabetical-ish with the existing `import os` / `import sys` group):

```python
import asyncio
import io
import os
import sys
import tempfile
import time
```

Change the two project imports (currently lines 42–43) to:

```python
from qwen_clone_tts import MAX_CHARS, MOOD_PRESETS, _try_daemon, resolve_instruct  # noqa: E402,F401
from say_moods import extract_mood, first_line_over_limit, parse_lines  # noqa: E402
from say_moods import MOOD_EMOJI  # noqa: E402
from stt_transcribe import WHISPER_MODEL, probe_duration, transcribe as run_stt  # noqa: E402
from transcribe_mood import detect_mood  # noqa: E402
```

After the `DEFAULT_VOICE = "Liino"` line (~line 50), add:

```python
# /transcribe limits (TTS-1005)
TRANSCRIBE_MAX_BYTES = 20 * 1024 * 1024
TRANSCRIBE_MAX_DURATION_S = 600
TRANSCRIBE_INLINE_MAX = 1800  # ยาวกว่านี้ -> ส่งเฉพาะไฟล์แนบ ไม่ preview ในแชท
```

- [ ] **Step 2: Add the `/transcribe` command**

Insert this immediately after the `say` function ends (the line before `def main() -> int:`):

```python
@tree.command(
    name="transcribe",
    description="ถอดเสียงไฟล์เสียงเป็นข้อความ + emoji mood พร้อมใช้กับ /say")
@app_commands.guild_only()
@app_commands.describe(
    file="ไฟล์เสียง .mp3 หรือ .wav (≤ 20 MB, ≤ 10 นาที)",
    mood="บังคับ mood ทุกบรรทัด (ไม่เลือก = auto จากข้อความ)")
@app_commands.choices(mood=[
    app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
async def transcribe(interaction: discord.Interaction,
                     file: discord.Attachment,
                     mood: str | None = None) -> None:
    # pre-defer validation — error ทุกจุดตรงนี้เป็น ephemeral, ไม่โพสต์ลงแชท
    if not file.filename.lower().endswith((".mp3", ".wav")):
        await interaction.response.send_message(
            "ไฟล์ต้องเป็น `.mp3` หรือ `.wav`", ephemeral=True)
        return
    if file.size > TRANSCRIBE_MAX_BYTES:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 20 MB", ephemeral=True)
        return

    # STT ช้ากว่า 3 วิแน่ -> defer ก่อน (spinner เห็นเฉพาะคนสั่ง)
    await interaction.response.defer(ephemeral=True, thinking=True)

    ext = ".mp3" if file.filename.lower().endswith(".mp3") else ".wav"
    audio_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_transcribe_{os.getpid()}_{int(time.time()*1000)}{ext}")
    try:
        try:
            await file.save(audio_path)
        except discord.DiscordException as e:  # noqa: BLE001
            await interaction.followup.send(
                f"ดาวน์โหลดไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
            return

        try:
            duration = await asyncio.to_thread(probe_duration, audio_path)
        except RuntimeError as e:
            print(f"discord_say_bot: transcribe probe error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                "อ่านไฟล์เสียงไม่สำเร็จ (ไฟล์เสียหายหรือไม่ใช่ไฟล์เสียง)",
                ephemeral=True)
            return
        if duration > TRANSCRIBE_MAX_DURATION_S:
            await interaction.followup.send(
                f"เสียงยาวเกิน 10 นาที ({duration / 60:.1f} นาที)",
                ephemeral=True)
            return

        t0 = time.time()
        try:
            lines = await asyncio.to_thread(run_stt, audio_path)
        except Exception as e:  # noqa: BLE001
            print(f"discord_say_bot: transcribe STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงไม่สำเร็จ: {e}", ephemeral=True)
            return
        stt_s = time.time() - t0

        if not lines:
            await interaction.followup.send(
                "ถอดเสียงไม่พบข้อความ (เสียงเงียบหรือไม่มีคำพูด)",
                ephemeral=True)
            return

        composed: list[str] = []
        for line in lines:
            m = mood or detect_mood(line)
            prefix = f"{MOOD_EMOJI[m]} " if m in MOOD_EMOJI else ""
            composed.append(f"{prefix}{line}")
        body = "\n".join(composed)

        txt = discord.File(
            io.BytesIO(body.encode("utf-8")),
            filename=f"transcribe_{interaction.id}.txt")
        if len(body) <= TRANSCRIBE_INLINE_MAX:
            await interaction.channel.send(f"```\n{body}\n```", file=txt)
        else:
            await interaction.channel.send(
                "📝 ถอดเสียงเสร็จแล้ว (ข้อความยาว — ดูไฟล์แนบ)", file=txt)
        await interaction.followup.send("✅ เสร็จแล้ว", ephemeral=True)
        print(f"discord_say_bot: transcribe guild={interaction.guild.id} "
              f"bytes={file.size} dur_s={duration:.1f} lines={len(lines)} "
              f"stt_s={stt_s:.2f} model={WHISPER_MODEL} explicit_mood={mood}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass
```

- [ ] **Step 3: Syntax + import check**

Run: `.venv/bin/python -c "import discord_say_bot"`
Expected: no output, exit 0 (module imports cleanly; command registers on the tree at import time).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — full suite (`test_say_moods.py`, `test_transcribe_mood.py`, `test_stt_transcribe.py`) green. No regression.

- [ ] **Step 4: Update `README.md` — env var table**

In the §Discord Bot "Config (environment variables)" table, add a row after the `SAY_SENTENCE_GAP_S` row:

```markdown
| `TRANSCRIBE_WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | Whisper model repo used by `/transcribe` for speech-to-text. The first `/transcribe` after startup downloads ~1.6 GB to the Hugging Face cache. Set to `mlx-community/whisper-large-v3` for higher accuracy at the cost of speed and memory. |
```

- [ ] **Step 5: Update `README.md` — `/transcribe` subsection**

Directly after the env-var table (before the `---` that closes §Discord Bot), add:

```markdown
### `/transcribe` — audio file → paste-ready `/say` text

Upload an `.mp3` or `.wav` and the bot transcribes it locally with Whisper
(`mlx-whisper`, no cloud), tags each line with a mood emoji, and replies with a
`.txt` attachment you can drop straight into `/say file:`.

- **`/transcribe file:<audio> [mood:<preset>]`** — `file` must be `.mp3` or
  `.wav`, ≤ 20 MB and ≤ 10 minutes; anything else is rejected with an ephemeral
  error and nothing is posted.
- Each Whisper segment becomes one line. A per-line keyword heuristic (Thai +
  English) picks a mood and prefixes the matching emoji (`😄`, `😢`, `🤫`, …) —
  the same emoji `/say` reads back as auto-mood. Lines with no match get no
  prefix.
- **`mood:<preset>`** overrides the mood for **every** line. `default` and
  `long` have no emoji, so choosing them emits lines with no prefix.
- The reply is always a `.txt` attachment. When the text is ≤ 1800 characters it
  is also shown inline in a code block; longer transcripts are attachment-only.
- This command never touches the TTS daemon — it works even when the daemon is
  down.
- First run downloads the Whisper model (~1.6 GB, see
  `TRANSCRIBE_WHISPER_MODEL`). It loads once and stays in the bot process.
```

Also: in the intro paragraph of §Discord Bot (line ~233) append one sentence — `A second command, /transcribe, converts an uploaded audio file into paste-ready /say text (see below).` — and in the top-of-README features table row for the Discord voice bot, append `; /transcribe turns an audio upload into paste-ready text` to the description cell.

- [ ] **Step 6: Commit**

```bash
git add discord_say_bot.py README.md
git commit -m "$(cat <<'EOF'
feat(TTS-1005): Add /transcribe slash command

Audio upload -> local Whisper STT -> per-line mood emoji -> .txt reply that
pastes into /say file:. Text only, no VC playback, no TTS daemon. 20 MB /
10 min limits, ephemeral errors. README + env table updated.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

- [ ] **Step 7: Manual / live validation** (record results in the ticket's Review Notes)

Prereqs: `DISCORD_BOT_TOKEN` (and ideally `DISCORD_GUILD_ID`) exported; `.venv/bin/python discord_say_bot.py` running. The TTS daemon is **not** required for `/transcribe` itself, but is needed for the round-trip check.

1. **Happy path (.mp3):** upload a real Thai `.mp3` → bot replies with a `.txt` (and inline block if short); text is a plausible transcription; lines with mood keywords carry the right emoji.
2. **Happy path (.wav):** repeat with a `.wav`.
3. **Round-trip:** download the `.txt`, run `/say file:` with it → Liino speaks each line, mood matching the emoji.
4. **`mood:` override:** `/transcribe file:<x.mp3> mood:excited` → every line prefixed `😄`.
5. **Reject — wrong type:** upload a `.pdf` (or `.txt`) → ephemeral "ไฟล์ต้องเป็น `.mp3` หรือ `.wav`", nothing in channel.
6. **Reject — too big:** upload a `.wav` > 20 MB → ephemeral "ไฟล์ใหญ่เกิน 20 MB".
7. **Reject — too long:** upload audio > 10 min → ephemeral "เสียงยาวเกิน 10 นาที …".
8. **Empty audio:** upload a silent clip → ephemeral "ถอดเสียงไม่พบข้อความ …".
9. **Long transcript:** upload audio whose transcript exceeds 1800 chars → reply is the note + attachment, no inline block, no crash.
10. **STT failure isolation:** restart the bot with `TRANSCRIBE_WHISPER_MODEL=bogus/nope`, run `/transcribe` → ephemeral "ถอดเสียงไม่สำเร็จ: …", bot stays up and `/say` still works. Reset the env var afterward.
11. **Daemon down:** stop `tts_daemon.py`, run `/transcribe` → still succeeds (text output unaffected).

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| §3.1 `stt_transcribe.py` (`transcribe`, `probe_duration`, `WHISPER_MODEL`) | Task 3 |
| §3.2 `transcribe_mood.py` (`MOOD_KEYWORDS`, `detect_mood`) | Task 2 |
| §3.3 `say_moods.MOOD_EMOJI` | Task 1 |
| §3.4 / §4 `/transcribe` command + flow (validate → defer → download → probe → STT → compose → reply → cleanup) | Task 4 Steps 1–3 |
| §5 error-handling table (ephemeral vs channel) | Task 4 Step 2 code + Step 7 cases 5–10 |
| §6 `requirements.txt` `mlx-whisper` pin | Task 3 Step 1 |
| §6 `TRANSCRIBE_WHISPER_MODEL` README env row | Task 4 Step 4 |
| §6 `/transcribe` README subsection, no new intent | Task 4 Step 5 (+ Global Constraints) |
| §7 automated tests (`MOOD_EMOJI` round-trip, `detect_mood` cases) | Task 1 Step 1, Task 2 Step 1 |
| §7 manual/live validation | Task 4 Step 7 |
| §8 risk: swap model via env var, no code change | Task 3 (`WHISPER_MODEL`), Task 4 Step 4 README note |

No gaps.

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Every code step has full code; the mood keyword table and `/say` intro-line edits are spelled out verbatim.

**3. Type consistency:**
- `MOOD_EMOJI: dict[str, str]` — defined Task 1, consumed Task 2 (test) and Task 4 (`MOOD_EMOJI[m]`, `m in MOOD_EMOJI`). Consistent.
- `detect_mood(text: str) -> str | None` — defined Task 2, called Task 4 as `mood or detect_mood(line)`. Consistent.
- `probe_duration(audio_path: str) -> float` raising `RuntimeError` — defined Task 3, caught as `RuntimeError` in Task 4. Consistent.
- `transcribe(audio_path: str) -> list[str]` — defined Task 3, imported `as run_stt` in Task 4, called `run_stt(audio_path)`, result used as `lines`. Consistent.
- `WHISPER_MODEL: str` — defined Task 3, imported and logged in Task 4. Consistent.

No issues found.
