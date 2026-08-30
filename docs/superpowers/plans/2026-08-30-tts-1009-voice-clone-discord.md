# TTS-1009 `/voice-clone` Discord Command Group — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Discord slash command group `/voice-clone` (create/list/edit/delete/test) so users can clone, inspect, edit, rename, delete, and audition voices entirely from Discord.

**Architecture:** New pure module `voice_store.py` owns all voice-file CRUD, name sanitization, and reference-audio preparation (no `discord` import — testable in isolation). `discord_say_bot.py` gains an `app_commands.Group` that calls `voice_store` plus the already-imported `run_stt` / `probe_duration` (Whisper STT) and `_try_daemon` (fast-path generation for `test`). `tts_daemon.py` and `qwen_clone_tts.py` are NOT touched — the daemon already resolves any `voice` name to `voices/<voice>.wav` + `.txt` and keys its cache on `voice`.

**Tech Stack:** Python 3.10+, `discord.py` (`app_commands`), `mlx-whisper` (via `stt_transcribe`), `ffmpeg`/`ffprobe` CLI, `pytest`.

## Global Constraints

- **Never use system `python3`** — all commands use `.venv/bin/python`. Python <3.10 fails silently (`str | None` syntax).
- Comments/docstrings in Thai; identifiers and log/error messages in English (match existing files).
- `voice_store.py` is an importer of `qwen_clone_tts.py` constants where relevant (`VOICES_DIR`) — do not duplicate `VOICES_DIR`; import it. It must not `import discord`.
- All subprocess calls pass argv as a **list**, never `shell=True`.
- Voice name rule: `^[a-z0-9_]{1,32}$` after lowercasing. Reject anything else (path traversal, spaces, emoji, empty).
- Reserved name: `liino` (case-insensitive). `create` onto it requires `overwrite=True`; `delete`/`rename` (old or new) targeting it is always rejected.
- Attachment size cap for `create`: 25 MB. Accepted extensions: `.mp3 .wav .m4a .ogg`.
- Reference audio minimum duration: 3.0 s (shorter → reject). Output: mono, 24000 Hz, `pcm_s16le`, first 12 s only.
- No new env vars, no new dependencies.
- Non-goals (do NOT implement here): `/say voice:` parameter and `resolve_instruct()` voice-default (→ TTS-1010); long-text chunking; multi-clip concat; role/permission gating.
- Tests live at repo root as `test_<module>.py` (pytest auto-discovers from root; no `tests/` dir, no `pyproject.toml`).

---

## File Structure

- **Create `voice_store.py`** — voice-file CRUD + sanitize + ref-audio prep. Pure, no `discord`.
- **Create `test_voice_store.py`** — unit tests for `voice_store`.
- **Modify `discord_say_bot.py`** — add `/voice-clone` group (5 subcommands); import `voice_store`.
- **Modify `README.md`** — `## Discord Bot` section: document `/voice-clone`.
- **Modify `CLAUDE.md`** — note `voice_store.py` in the architecture / module-boundary paragraph.

---

## Task 1: `voice_store.py` — name sanitization + reserved-name gate

**Files:**
- Create: `voice_store.py`
- Test: `test_voice_store.py`

**Interfaces:**
- Consumes: `VOICES_DIR` from `qwen_clone_tts`.
- Produces:
  - `VOICE_NAME_RE: re.Pattern` — compiled `^[a-z0-9_]{1,32}$`
  - `RESERVED: frozenset[str]` — `frozenset({"liino"})`
  - `class VoiceStoreError(Exception)` — raised for every user-facing failure; message is English, safe to show in Discord.
  - `sanitize_name(raw: str) -> str` — lowercase + strip; raises `VoiceStoreError` if the result doesn't match `VOICE_NAME_RE`.
  - `is_reserved(name: str) -> bool` — `name.lower() in RESERVED`.

- [ ] **Step 1: Write the failing test**

```python
# test_voice_store.py
import pytest
import voice_store
from voice_store import sanitize_name, is_reserved, VoiceStoreError


@pytest.mark.parametrize("raw,expected", [
    ("Liino", "liino"),
    ("  Wyitz  ", "wyitz"),
    ("my_voice_2", "my_voice_2"),
    ("ABC123", "abc123"),
])
def test_sanitize_name_ok(raw, expected):
    assert sanitize_name(raw) == expected


@pytest.mark.parametrize("raw", [
    "../etc", "a/b", "has space", "emoji😀", "", "   ",
    "a" * 33, "dash-name", "dot.name",
])
def test_sanitize_name_rejects(raw):
    with pytest.raises(VoiceStoreError):
        sanitize_name(raw)


def test_is_reserved():
    assert is_reserved("liino") is True
    assert is_reserved("LIINO") is True
    assert is_reserved("wyitz") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_store'`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Voice-clone file store สำหรับ /voice-clone (TTS-1009) — pure, ไม่ import discord

จัดการไฟล์ใน voices/<name>.{wav,txt,instruct.txt}:
  <name>.wav          เสียงอ้างอิงสำหรับโคลน (mono 24kHz)
  <name>.txt          transcript ของเสียงอ้างอิง (จาก Whisper) — ช่วย cloning
  <name>.instruct.txt  default voice instruction (optional)

ชื่อเสียงถูกจำกัดที่ [a-z0-9_]{1,32} เพื่อกัน path traversal / อักขระแปลก
"liino" เป็น reserved ห้ามลบ/rename และ create ทับต้องใส่ overwrite=True
"""
import os
import re
import subprocess

from qwen_clone_tts import VOICES_DIR

VOICE_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
RESERVED = frozenset({"liino"})


class VoiceStoreError(Exception):
    """error ที่ปลอดภัยจะแสดงให้ผู้ใช้ Discord เห็น (ข้อความเป็น English)"""


def sanitize_name(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not VOICE_NAME_RE.match(name):
        raise VoiceStoreError(
            "voice name must be 1-32 chars of a-z, 0-9, underscore only")
    return name


def is_reserved(name: str) -> bool:
    return name.lower() in RESERVED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add voice_store.py test_voice_store.py
git commit -m "feat(TTS-1009): voice_store.sanitize_name + reserved-name gate"
```

---

## Task 2: `voice_store.py` — path helpers, list, instruction read/write

**Files:**
- Modify: `voice_store.py`
- Test: `test_voice_store.py`

**Interfaces:**
- Consumes: `sanitize_name`, `VOICES_DIR`.
- Produces:
  - `voice_paths(name: str) -> tuple[str, str, str]` — returns absolute `(wav, txt, instruct_txt)` for a sanitized name. Does NOT check existence. Paths: `VOICES_DIR/<name>.wav`, `.txt`, `.instruct.txt`.
  - `voice_exists(name: str) -> bool` — True iff the `.wav` exists.
  - `read_instruction(name: str) -> str | None` — contents of `<name>.instruct.txt` stripped, or `None` if the file is absent/empty.
  - `write_instruction(name: str, text: str) -> None` — writes `<name>.instruct.txt` (UTF-8). Empty/whitespace `text` → delete the file if present (no-op if absent).
  - `list_voices() -> list[dict]` — one dict per `voices/*.wav` (excluding `.gitkeep`), sorted by name: `{"name": str, "has_transcript": bool, "instruction": str | None}`.

- [ ] **Step 1: Write the failing test**

```python
# append to test_voice_store.py
import voice_store as vs


@pytest.fixture
def voices_dir(tmp_path, monkeypatch):
    d = tmp_path / "voices"
    d.mkdir()
    monkeypatch.setattr(vs, "VOICES_DIR", str(d))
    return d


def _touch(p, content=""):
    p.write_text(content, encoding="utf-8")


def test_voice_paths_shape(voices_dir):
    wav, txt, ins = vs.voice_paths("wyitz")
    assert wav.endswith("/wyitz.wav")
    assert txt.endswith("/wyitz.txt")
    assert ins.endswith("/wyitz.instruct.txt")
    assert os.path.isabs(wav)


def test_voice_exists(voices_dir):
    assert vs.voice_exists("wyitz") is False
    _touch(voices_dir / "wyitz.wav", "x")
    assert vs.voice_exists("wyitz") is True


def test_instruction_round_trip(voices_dir):
    assert vs.read_instruction("wyitz") is None
    vs.write_instruction("wyitz", "  calm, warm, slow pacing  ")
    assert vs.read_instruction("wyitz") == "calm, warm, slow pacing"
    vs.write_instruction("wyitz", "   ")
    assert vs.read_instruction("wyitz") is None
    assert not (voices_dir / "wyitz.instruct.txt").exists()


def test_list_voices(voices_dir):
    _touch(voices_dir / ".gitkeep")
    _touch(voices_dir / "liino.wav", "x")
    _touch(voices_dir / "liino.txt", "hello")
    _touch(voices_dir / "wyitz.wav", "x")
    _touch(voices_dir / "wyitz.instruct.txt", "grumpy, clipped")
    got = vs.list_voices()
    assert [v["name"] for v in got] == ["liino", "wyitz"]
    assert got[0] == {"name": "liino", "has_transcript": True,
                      "instruction": None}
    assert got[1] == {"name": "wyitz", "has_transcript": False,
                      "instruction": "grumpy, clipped"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: FAIL — `AttributeError: module 'voice_store' has no attribute 'voice_paths'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to voice_store.py

def voice_paths(name: str) -> tuple[str, str, str]:
    base = os.path.join(VOICES_DIR, name)
    return (os.path.abspath(base + ".wav"),
            os.path.abspath(base + ".txt"),
            os.path.abspath(base + ".instruct.txt"))


def voice_exists(name: str) -> bool:
    return os.path.exists(voice_paths(name)[0])


def read_instruction(name: str) -> str | None:
    _, _, ins = voice_paths(name)
    if not os.path.exists(ins):
        return None
    with open(ins, "r", encoding="utf-8") as f:
        text = f.read().strip()
    return text or None


def write_instruction(name: str, text: str) -> None:
    _, _, ins = voice_paths(name)
    text = (text or "").strip()
    if not text:
        if os.path.exists(ins):
            os.remove(ins)
        return
    with open(ins, "w", encoding="utf-8") as f:
        f.write(text + "\n")


def list_voices() -> list[dict]:
    if not os.path.isdir(VOICES_DIR):
        return []
    names = sorted(
        f[:-4] for f in os.listdir(VOICES_DIR)
        if f.endswith(".wav"))
    out: list[dict] = []
    for name in names:
        _, txt, _ = voice_paths(name)
        out.append({
            "name": name,
            "has_transcript": os.path.exists(txt),
            "instruction": read_instruction(name),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add voice_store.py test_voice_store.py
git commit -m "feat(TTS-1009): voice_store path helpers + list_voices + instruction io"
```

---

## Task 3: `voice_store.py` — rename + delete

**Files:**
- Modify: `voice_store.py`
- Test: `test_voice_store.py`

**Interfaces:**
- Consumes: `sanitize_name`, `is_reserved`, `voice_paths`, `voice_exists`.
- Produces:
  - `rename_voice(old: str, new: str) -> None` — `old`/`new` are already-sanitized names. Raises `VoiceStoreError` if: `old` doesn't exist, `old` or `new` is reserved, `new` already exists. Moves whichever of the 3 files exist (`.wav`, `.txt`, `.instruct.txt`) from `old` to `new`.
  - `delete_voice(name: str) -> list[str]` — `name` already sanitized. Raises `VoiceStoreError` if reserved or the voice doesn't exist. Removes whichever of the 3 files exist; returns the basenames removed.

- [ ] **Step 1: Write the failing test**

```python
# append to test_voice_store.py

def test_rename_voice_moves_all_files(voices_dir):
    _touch(voices_dir / "old.wav", "w")
    _touch(voices_dir / "old.txt", "t")
    _touch(voices_dir / "old.instruct.txt", "i")
    vs.rename_voice("old", "new")
    assert not (voices_dir / "old.wav").exists()
    assert (voices_dir / "new.wav").read_text() == "w"
    assert (voices_dir / "new.txt").read_text() == "t"
    assert (voices_dir / "new.instruct.txt").read_text() == "i"


def test_rename_voice_partial_files_ok(voices_dir):
    _touch(voices_dir / "old.wav", "w")  # no .txt / .instruct.txt
    vs.rename_voice("old", "new")
    assert (voices_dir / "new.wav").exists()
    assert not (voices_dir / "new.txt").exists()


def test_rename_voice_rejects(voices_dir):
    _touch(voices_dir / "old.wav", "w")
    _touch(voices_dir / "taken.wav", "w")
    with pytest.raises(vs.VoiceStoreError):
        vs.rename_voice("missing", "new")
    with pytest.raises(vs.VoiceStoreError):
        vs.rename_voice("old", "taken")
    with pytest.raises(vs.VoiceStoreError):
        vs.rename_voice("old", "liino")
    with pytest.raises(vs.VoiceStoreError):
        vs.rename_voice("liino", "new")


def test_delete_voice(voices_dir):
    _touch(voices_dir / "gone.wav", "w")
    _touch(voices_dir / "gone.txt", "t")
    removed = vs.delete_voice("gone")
    assert set(removed) == {"gone.wav", "gone.txt"}
    assert not (voices_dir / "gone.wav").exists()


def test_delete_voice_rejects(voices_dir):
    with pytest.raises(vs.VoiceStoreError):
        vs.delete_voice("liino")
    with pytest.raises(vs.VoiceStoreError):
        vs.delete_voice("missing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: FAIL — `AttributeError: module 'voice_store' has no attribute 'rename_voice'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to voice_store.py

def rename_voice(old: str, new: str) -> None:
    if is_reserved(old) or is_reserved(new):
        raise VoiceStoreError("cannot rename to or from a reserved voice name")
    if not voice_exists(old):
        raise VoiceStoreError(f"voice '{old}' not found")
    if voice_exists(new):
        raise VoiceStoreError(f"voice '{new}' already exists")
    for src, dst in zip(voice_paths(old), voice_paths(new)):
        if os.path.exists(src):
            os.rename(src, dst)


def delete_voice(name: str) -> list[str]:
    if is_reserved(name):
        raise VoiceStoreError("cannot delete a reserved voice name")
    if not voice_exists(name):
        raise VoiceStoreError(f"voice '{name}' not found")
    removed: list[str] = []
    for p in voice_paths(name):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add voice_store.py test_voice_store.py
git commit -m "feat(TTS-1009): voice_store rename_voice + delete_voice with reserved guard"
```

---

## Task 4: `voice_store.py` — `prepare_ref_audio` (ffmpeg convert + trim)

**Files:**
- Modify: `voice_store.py`
- Test: `test_voice_store.py`

**Interfaces:**
- Consumes: `probe_duration` from `stt_transcribe`, `VoiceStoreError`.
- Produces:
  - `MIN_REF_SECONDS: float` = `3.0`
  - `REF_TRIM_SECONDS: int` = `12`
  - `prepare_ref_audio(src_path: str, dst_wav: str) -> float` — probes `src_path` duration; raises `VoiceStoreError` if `< MIN_REF_SECONDS` or ffprobe fails. Runs ffmpeg to write `dst_wav` as mono / 24000 Hz / `pcm_s16le`, taking only the first `REF_TRIM_SECONDS`. Raises `VoiceStoreError` if ffmpeg exits nonzero or `dst_wav` is missing. Returns the source duration in seconds.

- [ ] **Step 1: Write the failing test**

```python
# append to test_voice_store.py
import shutil
import subprocess

_ffmpeg_missing = (shutil.which("ffmpeg") is None
                   or shutil.which("ffprobe") is None)
pytestmark_ffmpeg = pytest.mark.skipif(
    _ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")


@pytestmark_ffmpeg
def test_prepare_ref_audio_rejects_short_clip(tmp_path):
    src = tmp_path / "short.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", str(src)], check=True)
    with pytest.raises(vs.VoiceStoreError):
        vs.prepare_ref_audio(str(src), str(tmp_path / "out.wav"))


@pytestmark_ffmpeg
def test_prepare_ref_audio_converts_and_trims(tmp_path):
    src = tmp_path / "long.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=20:sample_rate=44100",
         "-ac", "2", str(src)], check=True)
    dst = tmp_path / "ref.wav"
    dur = vs.prepare_ref_audio(str(src), str(dst))
    assert 19.5 < dur < 20.5
    assert dst.exists()
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=channels,sample_rate", "-of", "csv=p=0", str(dst)],
        capture_output=True, text=True, check=True).stdout
    assert "1" in out and "24000" in out
    assert vs.probe_duration_seconds(str(dst)) <= 12.2
```

Note: the test uses `vs.probe_duration_seconds` — expose `probe_duration` from `stt_transcribe` under that alias in `voice_store` (Step 3) so tests don't import `stt_transcribe` directly.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: FAIL — `AttributeError: module 'voice_store' has no attribute 'prepare_ref_audio'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to voice_store.py — near the top imports
from stt_transcribe import probe_duration as probe_duration_seconds

# ... with the other module constants
MIN_REF_SECONDS = 3.0
REF_TRIM_SECONDS = 12


def prepare_ref_audio(src_path: str, dst_wav: str) -> float:
    """แปลงไฟล์เสียงอ้างอิงเป็น mono 24kHz wav ตัดต้นคลิป REF_TRIM_SECONDS วิ

    raise VoiceStoreError ถ้าไฟล์สั้นกว่า MIN_REF_SECONDS, probe ไม่ได้,
    หรือ ffmpeg ล้มเหลว คืนความยาว (วินาที) ของไฟล์ต้นทาง
    """
    try:
        duration = probe_duration_seconds(src_path)
    except RuntimeError as e:
        raise VoiceStoreError(f"cannot read audio file: {e}") from e
    if duration < MIN_REF_SECONDS:
        raise VoiceStoreError(
            f"reference clip too short ({duration:.1f}s) — "
            f"need at least {MIN_REF_SECONDS:.0f}s")
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src_path, "-t", str(REF_TRIM_SECONDS),
         "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", dst_wav],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst_wav):
        raise VoiceStoreError(f"ffmpeg convert failed: {r.stderr.strip()}")
    return duration
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_voice_store.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add voice_store.py test_voice_store.py
git commit -m "feat(TTS-1009): voice_store.prepare_ref_audio — ffmpeg mono/24k/trim + min-duration guard"
```

---

## Task 5: `discord_say_bot.py` — `/voice-clone` group scaffold + `list` + `delete`

**Files:**
- Modify: `discord_say_bot.py` (imports near line 45-48; new group + subcommands after the `transcribe` command, before `def main`)
- Test: manual (Discord) — no pytest (discord.py command bodies aren't unit-tested in this repo; see `test_stt_transcribe.py` header note).

**Interfaces:**
- Consumes: `voice_store` (`sanitize_name`, `is_reserved`, `list_voices`, `delete_voice`, `voice_exists`, `VoiceStoreError`).
- Produces: an `app_commands.Group` instance named `voice-clone` registered on `tree`, with subcommands `list` and `delete` working. `create`/`edit`/`test` added in later tasks.

- [ ] **Step 1: Add the import**

In `discord_say_bot.py`, after the existing `from stt_transcribe import ...` line (~line 47), add:

```python
import voice_store  # noqa: E402
from voice_store import VoiceStoreError  # noqa: E402
```

- [ ] **Step 2: Define the group and register it**

After the `transcribe` function (before `def main()`), add:

```python
voice_clone = app_commands.Group(
    name="voice-clone",
    description="สร้าง/จัดการเสียงโคลนสำหรับ /say (create/list/edit/delete/test)",
    guild_only=True)
tree.add_command(voice_clone)


def _voices_summary() -> str:
    voices = voice_store.list_voices()
    if not voices:
        return "ยังไม่มีเสียงใน voices/"
    rows = []
    for v in voices:
        tag = "" if v["has_transcript"] else " (ไม่มี transcript)"
        ins = f" — {v['instruction']}" if v["instruction"] else ""
        rows.append(f"• {v['name']}{tag}{ins}")
    return "\n".join(rows)


@voice_clone.command(name="list", description="แสดงเสียงทั้งหมดใน voices/")
async def voice_clone_list(interaction: discord.Interaction) -> None:
    body = _voices_summary().replace("```", "`​`​`")
    await interaction.response.send_message(
        f"🎙️ เสียงที่มี:\n```\n{body}\n```", ephemeral=True)


@voice_clone.command(name="delete", description="ลบเสียง (ต้อง confirm:true)")
@app_commands.describe(name="ชื่อเสียงที่จะลบ", confirm="ต้องใส่ true เพื่อยืนยัน")
async def voice_clone_delete(interaction: discord.Interaction, name: str,
                             confirm: bool = False) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not confirm:
        await interaction.response.send_message(
            f"⚠️ ยืนยันด้วย `/voice-clone delete name:{clean} confirm:true`",
            ephemeral=True)
        return
    try:
        removed = voice_store.delete_voice(clean)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🗑️ ลบเสียง `{clean}` แล้ว ({', '.join(removed)})", ephemeral=True)
    print(f"discord_say_bot: voice-clone delete guild={interaction.guild.id} "
          f"name={clean} removed={removed}", file=sys.stderr, flush=True)
```

- [ ] **Step 3: Sanity-check the module imports**

Run: `.venv/bin/python -c "import discord_say_bot"`
Expected: no output, exit 0 (import succeeds — no token needed for import).

- [ ] **Step 4: Run the full test suite (regression)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (same count as before + the new `test_voice_store.py` tests).

- [ ] **Step 5: Commit**

```bash
git add discord_say_bot.py
git commit -m "feat(TTS-1009): /voice-clone group + list + delete subcommands"
```

---

## Task 6: `discord_say_bot.py` — `/voice-clone create`

**Files:**
- Modify: `discord_say_bot.py` (add subcommand in the `voice_clone` group)
- Test: manual (Discord)

**Interfaces:**
- Consumes: `voice_store.sanitize_name/is_reserved/voice_exists/voice_paths/prepare_ref_audio/write_instruction`, `run_stt` (already imported as `from stt_transcribe import ... transcribe as run_stt`), `VoiceStoreError`.
- Produces: `/voice-clone create name file [instruction] [overwrite]` that writes `voices/<name>.wav` + `.txt` (+ `.instruct.txt`).

- [ ] **Step 1: Add module constant near the other `/transcribe` limits (~line 60)**

```python
# /voice-clone create limits (TTS-1009)
VOICE_CLONE_MAX_BYTES = 25 * 1024 * 1024
VOICE_CLONE_EXTS = (".mp3", ".wav", ".m4a", ".ogg")
```

- [ ] **Step 2: Add the subcommand (in the `voice_clone` group, after `voice_clone_list`)**

```python
@voice_clone.command(
    name="create", description="โคลนเสียงใหม่จากไฟล์เสียงที่อัปโหลด")
@app_commands.describe(
    name="ชื่อเสียง (a-z, 0-9, _ เท่านั้น)",
    file="ไฟล์เสียงอ้างอิง .mp3/.wav/.m4a/.ogg (≤ 25 MB, ≥ 3 วิ)",
    instruction="คำบรรยายน้ำเสียงประจำตัวละคร (สั้น, อังกฤษ) — optional",
    overwrite="ทับเสียงชื่อเดิมถ้ามีอยู่แล้ว")
async def voice_clone_create(interaction: discord.Interaction, name: str,
                             file: discord.Attachment,
                             instruction: str | None = None,
                             overwrite: bool = False) -> None:
    # pre-defer validation — ephemeral ทั้งหมด
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not file.filename.lower().endswith(VOICE_CLONE_EXTS):
        await interaction.response.send_message(
            f"ไฟล์ต้องเป็น {', '.join(VOICE_CLONE_EXTS)}", ephemeral=True)
        return
    if file.size > VOICE_CLONE_MAX_BYTES:
        await interaction.response.send_message(
            "ไฟล์ใหญ่เกิน 25 MB", ephemeral=True)
        return
    if voice_store.voice_exists(clean) and not overwrite:
        await interaction.response.send_message(
            f"⚠️ เสียง `{clean}` มีอยู่แล้ว — ใส่ `overwrite:true` เพื่อทับ",
            ephemeral=True)
        return
    if voice_store.is_reserved(clean) and not overwrite:
        await interaction.response.send_message(
            f"⚠️ `{clean}` เป็นเสียง default — ใส่ `overwrite:true` ถ้าตั้งใจจริง",
            ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    ext = os.path.splitext(file.filename.lower())[1]
    src_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_vc_{os.getpid()}_{int(time.time()*1000)}{ext}")
    wav_path, txt_path, _ = voice_store.voice_paths(clean)
    try:
        try:
            await file.save(src_path)
        except discord.DiscordException as e:  # noqa: BLE001
            await interaction.followup.send(
                f"ดาวน์โหลดไฟล์ไม่สำเร็จ: {e}", ephemeral=True)
            return
        try:
            dur = await asyncio.to_thread(
                voice_store.prepare_ref_audio, src_path, wav_path)
        except VoiceStoreError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
            return
        try:
            lines = await asyncio.to_thread(run_stt, wav_path, None)
        except Exception as e:  # noqa: BLE001
            os.remove(wav_path)
            print(f"discord_say_bot: voice-clone STT error: {e}",
                  file=sys.stderr, flush=True)
            await interaction.followup.send(
                f"ถอดเสียงอ้างอิงไม่สำเร็จ: {e}", ephemeral=True)
            return
        transcript = " ".join(lines).strip()
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript + "\n")
        if instruction:
            voice_store.write_instruction(clean, instruction)

        preview = transcript or "(ถอดเสียงไม่พบข้อความ — เสียงอาจไม่มีคำพูด)"
        safe = preview.replace("```", "`​`​`")
        await interaction.followup.send(
            f"✅ สร้างเสียง `{clean}` แล้ว ({dur:.1f}s ต้นฉบับ)\n"
            f"ตรวจ transcript ที่ถอดได้ (แก้ที่ `voices/{clean}.txt` ได้):\n"
            f"```\n{safe}\n```", ephemeral=True)
        print(f"discord_say_bot: voice-clone create guild={interaction.guild.id} "
              f"name={clean} src_bytes={file.size} dur_s={dur:.1f} "
              f"transcript_len={len(transcript)} instruction={bool(instruction)}",
              file=sys.stderr, flush=True)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass
```

- [ ] **Step 3: Sanity-check imports**

Run: `.venv/bin/python -c "import discord_say_bot"`
Expected: exit 0.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_say_bot.py
git commit -m "feat(TTS-1009): /voice-clone create — ref prep + Whisper transcript + instruct.txt"
```

---

## Task 7: `discord_say_bot.py` — `/voice-clone edit`

**Files:**
- Modify: `discord_say_bot.py`
- Test: manual (Discord)

**Interfaces:**
- Consumes: `voice_store.sanitize_name/voice_exists/is_reserved/write_instruction/rename_voice`, `VoiceStoreError`.
- Produces: `/voice-clone edit name [instruction] [rename]` — updates the `.instruct.txt` and/or renames the voice's files.

- [ ] **Step 1: Add the subcommand**

```python
@voice_clone.command(
    name="edit", description="แก้ instruction หรือเปลี่ยนชื่อเสียง")
@app_commands.describe(
    name="ชื่อเสียงปัจจุบัน",
    instruction="instruction ใหม่ (ส่งค่าว่างเพื่อลบ instruction เดิม)",
    rename="ชื่อใหม่ (a-z, 0-9, _)")
async def voice_clone_edit(interaction: discord.Interaction, name: str,
                           instruction: str | None = None,
                           rename: str | None = None) -> None:
    if instruction is None and rename is None:
        await interaction.response.send_message(
            "ต้องระบุอย่างน้อย `instruction:` หรือ `rename:`", ephemeral=True)
        return
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return

    changes: list[str] = []
    # instruction ก่อน (ตอนนี้ยังใช้ชื่อเดิม) — rename ทีหลังจะย้าย .instruct.txt ไปด้วย
    if instruction is not None:
        if voice_store.is_reserved(clean):
            await interaction.response.send_message(
                f"⚠️ แก้ instruction ของ `{clean}` (default voice) ไม่ได้",
                ephemeral=True)
            return
        voice_store.write_instruction(clean, instruction)
        changes.append("instruction ถูกลบ" if not instruction.strip()
                       else "instruction อัปเดตแล้ว")

    final_name = clean
    if rename is not None:
        try:
            new_clean = voice_store.sanitize_name(rename)
            voice_store.rename_voice(clean, new_clean)
        except VoiceStoreError as e:
            await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
            return
        final_name = new_clean
        changes.append(f"เปลี่ยนชื่อเป็น `{new_clean}`")

    await interaction.response.send_message(
        f"✏️ `{clean}`: " + ", ".join(changes), ephemeral=True)
    print(f"discord_say_bot: voice-clone edit guild={interaction.guild.id} "
          f"name={clean} -> {final_name} changes={changes}",
          file=sys.stderr, flush=True)
```

- [ ] **Step 2: Sanity-check imports**

Run: `.venv/bin/python -c "import discord_say_bot"`
Expected: exit 0.

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add discord_say_bot.py
git commit -m "feat(TTS-1009): /voice-clone edit — instruction update + rename"
```

---

## Task 8: `discord_say_bot.py` — `/voice-clone test`

**Files:**
- Modify: `discord_say_bot.py`
- Test: manual (Discord)

**Interfaces:**
- Consumes: `voice_store.sanitize_name/voice_exists/read_instruction`, `_try_daemon` (already imported), `MOOD_PRESETS` (already imported), `resolve_instruct` is NOT used here — instruct is resolved inline: `mood preset > voice instruction > MOOD_PRESETS["default"]`.
- Produces: `/voice-clone test name [text] [mood]` — generates a sample clip with the voice and posts the audio file.

- [ ] **Step 1: Add module constant near the other `/voice-clone` constants**

```python
VOICE_CLONE_TEST_TEXT = "สวัสดีค่ะ นี่คือตัวอย่างเสียงพูดจากเสียงโคลนนี้"
```

- [ ] **Step 2: Add the subcommand**

```python
@voice_clone.command(
    name="test", description="ทดลองสร้างเสียงพูดด้วยเสียงนี้")
@app_commands.describe(
    name="ชื่อเสียงที่จะทดสอบ",
    text="ข้อความทดสอบ (ไม่ระบุ = ประโยคเริ่มต้น)",
    mood="โทนเสียง (ไม่ระบุ = ใช้ instruction ประจำเสียง หรือ default)")
@app_commands.choices(
    mood=[app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
async def voice_clone_test(interaction: discord.Interaction, name: str,
                           text: str | None = None,
                           mood: str | None = None) -> None:
    try:
        clean = voice_store.sanitize_name(name)
    except VoiceStoreError as e:
        await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
        return
    if not voice_store.voice_exists(clean):
        await interaction.response.send_message(
            f"⚠️ ไม่พบเสียง `{clean}`", ephemeral=True)
        return
    spoken = (text or VOICE_CLONE_TEST_TEXT).strip()
    if len(spoken) > MAX_CHARS:
        await interaction.response.send_message(
            f"ข้อความยาวเกิน {MAX_CHARS} ตัวอักษร", ephemeral=True)
        return
    # instruct: mood > voice instruction > default (ไม่แตะ resolve_instruct — TTS-1010)
    if mood:
        instruct = MOOD_PRESETS[mood]
    else:
        instruct = voice_store.read_instruction(clean) or MOOD_PRESETS["default"]

    await interaction.response.defer(ephemeral=True, thinking=True)
    wav_path = os.path.join(
        tempfile.gettempdir(),
        f"qwen_vctest_{os.getpid()}_{int(time.time()*1000)}.wav")
    t0 = time.time()
    ok = await asyncio.to_thread(
        _try_daemon, spoken, wav_path, instruct, clean, "wav", "auto")
    gen_s = time.time() - t0
    if not ok:
        try:
            os.remove(wav_path)
        except OSError:
            pass
        await interaction.followup.send(
            "⚠️ TTS daemon ไม่พร้อมใช้งาน หรือสร้างเสียงไม่สำเร็จ", ephemeral=True)
        return
    try:
        await interaction.followup.send(
            f"🎧 ตัวอย่างเสียง `{clean}` (gen {gen_s:.1f}s)",
            file=discord.File(wav_path, filename=f"{clean}_test.wav"),
            ephemeral=True)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
    print(f"discord_say_bot: voice-clone test guild={interaction.guild.id} "
          f"name={clean} mood={mood} chars={len(spoken)} gen_s={gen_s:.2f}",
          file=sys.stderr, flush=True)
```

- [ ] **Step 3: Sanity-check imports**

Run: `.venv/bin/python -c "import discord_say_bot"`
Expected: exit 0.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add discord_say_bot.py
git commit -m "feat(TTS-1009): /voice-clone test — daemon fast-path sample generation"
```

---

## Task 9: Docs — README + CLAUDE.md

**Files:**
- Modify: `README.md` (`## Discord Bot` section ~line 252; Features table row ~line 29)
- Modify: `CLAUDE.md` (Architecture paragraph naming importers of `qwen_clone_tts.py`)

- [ ] **Step 1: Update the Features table row (`README.md` ~line 29)**

Change the `Discord voice bot` row's description to append:
`; /voice-clone create/list/edit/delete/test manages cloned voices from Discord (upload a clip → auto-transcribed reference)`

- [ ] **Step 2: Add a `/voice-clone` subsection to `## Discord Bot`**

After the `### /transcribe` subsection (~line 322-348), add:

```markdown
### `/voice-clone` — manage cloned voices from Discord

A command group for creating and managing the voices in `voices/` without
touching the filesystem by hand. All subcommands are guild-only and replies
are ephemeral (only the caller sees them).

- **`/voice-clone create name:<name> file:<audio> [instruction:<text>] [overwrite:<bool>]`**
  — uploads a reference clip (`.mp3/.wav/.m4a/.ogg`, ≤ 25 MB, ≥ 3 s). The clip
  is converted to mono 24 kHz and trimmed to the first 12 s, saved as
  `voices/<name>.wav`, then transcribed with Whisper into `voices/<name>.txt`
  (improves cloning). An optional `instruction` (short English tone
  description, same style as `MOOD_PRESETS`) is stored in
  `voices/<name>.instruct.txt`. Names are limited to `a-z 0-9 _` (1-32 chars).
  `Liino` is protected — overwriting it needs `overwrite:true`.
- **`/voice-clone list`** — lists every voice with its transcript status and
  stored instruction.
- **`/voice-clone edit name:<name> [instruction:<text>] [rename:<new>]`** —
  updates the stored instruction (send an empty `instruction` to clear it)
  and/or renames the voice (moves `.wav` / `.txt` / `.instruct.txt` together).
- **`/voice-clone delete name:<name> confirm:<true>`** — removes all three
  files. `confirm:true` is required; `Liino` cannot be deleted.
- **`/voice-clone test name:<name> [text:<text>] [mood:<preset>]`** —
  generates a short sample with that voice via the daemon fast path and posts
  the `.wav`. Instruction priority: `mood` preset > the voice's stored
  instruction > default.

The `/voice-clone` file operations live in `voice_store.py` (pure, no
`discord` import) so they're unit-tested independently of the bot.
```

- [ ] **Step 3: Update `CLAUDE.md`**

In the Architecture section, the sentence listing importers of `qwen_clone_tts.py` (`both tts_daemon.py and tune_voice.py import from it`) — extend the importer list to include `voice_store.py` (imports `VOICES_DIR`) and note `discord_say_bot.py` imports the new `voice_store` module for `/voice-clone`.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(TTS-1009): document /voice-clone command group + voice_store module"
```

---

## Task 10: Manual validation on Discord + full regression

**Files:** none (validation only)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS. Record the count in the ticket's Review Notes.

- [ ] **Step 2: Start the daemon and bot**

```bash
.venv/bin/python tts_daemon.py &
export DISCORD_BOT_TOKEN=...   # (and DISCORD_GUILD_ID for instant registration)
.venv/bin/python discord_say_bot.py
```

- [ ] **Step 3: Exercise every subcommand in a real guild**

- `/voice-clone create name:testvoice file:<a real mp3, ~10s>` → expect a
  reply with the transcript; verify `voices/testvoice.wav` + `.txt` exist.
- `/voice-clone create name:testvoice file:<same>` (no overwrite) → rejected.
- `/voice-clone create name:Liino file:<same>` (no overwrite) → rejected.
- `/voice-clone create name:../x file:<same>` → rejected (bad name).
- `/voice-clone list` → shows `testvoice` and `liino`.
- `/voice-clone test name:testvoice` → posts a `.wav` that plays in the new voice.
- `/voice-clone test name:testvoice mood:excited` → audibly different tone.
- `/voice-clone edit name:testvoice instruction:"calm, warm, slow pacing"` →
  confirm; then `/voice-clone test name:testvoice` uses the new tone.
- `/voice-clone edit name:testvoice rename:testvoice2` → confirm; `list`
  shows `testvoice2`, files renamed.
- `/voice-clone delete name:testvoice2` (no confirm) → asks for confirm.
- `/voice-clone delete name:testvoice2 confirm:true` → removed.
- `/voice-clone delete name:liino confirm:true` → rejected.

- [ ] **Step 4: Regression — existing commands unchanged**

- `/say text:"ทดสอบ"` (in a voice channel) → still speaks with Liino.
- `/transcribe file:<audio>` → still returns paste-ready text.

- [ ] **Step 5: Fill in the ticket's Review Notes and move to review**

Follow the kanban flow `/kanban move-review TTS-1009` (adds Review Notes,
opens the PR, moves the board entry).

---

## Self-Review

**Spec coverage:**
- `/voice-clone create` (ffmpeg trim + Whisper + instruct.txt) → Task 4 + Task 6 ✅
- create dup/reserved guard → Task 6 Step 2 ✅
- `/say voice:` → explicitly deferred to TTS-1010 (Global Constraints) ✅
- instruct priority `mood > voice instruction > default` → Task 8 (inline, unit-covered indirectly via `read_instruction` tests in Task 2); the full `resolve_instruct()` refactor + its unit test is TTS-1010 ✅
- `/voice-clone edit` instruction + rename → Task 7 ✅
- `/voice-clone list` / `delete` / `test`, delete-Liino guard → Tasks 5, 8 ✅
- name sanitize/reject (`../x`, space, emoji) → Task 1 ✅
- `pytest -q` green → Tasks 5-10 Steps ✅

**Placeholder scan:** none — every code step has complete code.

**Type consistency:** `voice_store` function names (`sanitize_name`, `is_reserved`, `voice_paths`, `voice_exists`, `read_instruction`, `write_instruction`, `list_voices`, `rename_voice`, `delete_voice`, `prepare_ref_audio`, `probe_duration_seconds`) are used identically across Tasks 5-8. `list_voices()` dict keys (`name`, `has_transcript`, `instruction`) match between Task 2 definition and Task 5 `_voices_summary`.

**Note on AC "resolve_instruct() ตัวใหม่":** the ticket's original AC referenced a new `resolve_instruct()` signature — that item moves to TTS-1010 along with `/say voice:`. TTS-1009's `test` subcommand resolves instruct inline and does not modify `qwen_clone_tts.py`.
