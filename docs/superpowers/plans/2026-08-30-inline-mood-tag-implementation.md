# Inline Mood Tag (`[mood:xxx]`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a single `--stdin` batch text file switch mood mid-file via inline
`[mood:xxx]` tags, generating each tagged segment separately and stitching the
results into one output file with ffmpeg.

**Architecture:** A new pure parser (`split_mood_segments()`) splits the input text
into `(mood_key | None, text_segment)` pairs and fail-fast-validates every mood key
against `MOOD_PRESETS` before any audio is generated. `main()`'s `--stdin` branch
dispatches on segment count: exactly one segment (the untagged case, or a single tag
covering everything) goes through the existing single-shot `_run()` unchanged; two or
more segments go through a new `_run_multi()` that generates one audio piece per
`chunk_text()`-sized chunk (trying the daemon first, in-process model load as
fallback) and concatenates them with ffmpeg. The daemon protocol (`tts_daemon.py`)
is untouched — it already accepts one `instruct` per request.

**Tech Stack:** Python 3.10+ stdlib (`re`, `tempfile`, `subprocess`), `ffmpeg` CLI
(already a hard dependency), `pytest` for tests, existing `_try_daemon()`/socket
protocol.

## Global Constraints

- Output contract is fixed and must not change: stdout gets exactly `OK <path>` on
  success; stderr gets `ERROR: ...` on failure plus a `TIMING ...` line either way
  (per `CLAUDE.md`).
- No daemon protocol change — `tts_daemon.py`'s `handle_request()` already accepts
  `instruct` per request (`tts_daemon.py:251`); do not touch that file.
- Untagged `--stdin` files (no `[mood:xxx]` anywhere) must be **byte-for-byte
  behaviorally identical** to today, including the hard `MAX_CHARS` (300) reject for
  oversized untagged text — this ticket does **not** enable blanket long-text
  auto-chunking for the plain `--text`/`--mood` CLI branch or single-segment `--stdin`
  calls. Only files that produce 2+ mood segments get the new chunk+concat path.
- Comments/docstrings in this codebase are Thai; identifiers and log/error messages
  are English (`CLAUDE.md`). Match this in every new function.
- Mood key matching is case-insensitive and lowercased before comparing against
  `MOOD_PRESETS`, matching `resolve_instruct()`'s existing `.strip().lower()`
  normalization (`qwen_clone_tts.py:98`).

---

### Task 1: `split_mood_segments()` — inline mood tag parser

**Files:**
- Modify: `qwen_clone_tts.py` — insert new code directly after `chunk_text()`
  (currently ends `qwen_clone_tts.py:143`), before `SOCK_PATH = ...`
  (`qwen_clone_tts.py:146`)
- Test: `test_qwen_clone_tts.py`

**Interfaces:**
- Consumes: `MOOD_PRESETS: dict[str, str]` (module-level, `qwen_clone_tts.py:30`)
- Produces: `split_mood_segments(text: str) -> list[tuple[str | None, str]]` — raises
  `ValueError` if the text contains any `[mood:xxx]` tag whose `xxx` is not a key in
  `MOOD_PRESETS`. Later tasks call this and iterate its return value.

- [ ] **Step 1: Write the failing tests**

Append to `test_qwen_clone_tts.py` (after `test_resolve_instruct_unknown_mood_raises`,
before the `class _FakeSock:` block):

```python
def test_split_mood_segments_no_tag_returns_single_none_segment():
    assert split_mood_segments("Hello world") == [(None, "Hello world")]


def test_split_mood_segments_single_tag_covers_whole_text():
    assert split_mood_segments("[mood:excited]Hello world") == \
        [("excited", "Hello world")]


def test_split_mood_segments_leading_text_then_tag():
    result = split_mood_segments("Hello [mood:excited] world")
    assert result == [(None, "Hello"), ("excited", "world")]


def test_split_mood_segments_multiple_tags_interleaved():
    text = "[mood:excited]Hi![mood:sleepy]So tired..."
    assert split_mood_segments(text) == \
        [("excited", "Hi!"), ("sleepy", "So tired...")]


def test_split_mood_segments_drops_empty_segment_between_adjacent_tags():
    text = "[mood:excited][mood:sleepy]only this"
    assert split_mood_segments(text) == [("sleepy", "only this")]


def test_split_mood_segments_drops_whitespace_only_segment():
    text = "[mood:excited]   \n  [mood:sleepy]only this"
    assert split_mood_segments(text) == [("sleepy", "only this")]


def test_split_mood_segments_lowercases_mood_key():
    assert split_mood_segments("[mood:EXCITED]hi") == [("excited", "hi")]


def test_split_mood_segments_unknown_mood_raises():
    with pytest.raises(ValueError):
        split_mood_segments("[mood:exicted]Hello")


def test_split_mood_segments_reports_all_unknown_moods_at_once():
    with pytest.raises(ValueError) as exc_info:
        split_mood_segments("[mood:foo]a[mood:bar]b")
    msg = str(exc_info.value)
    assert "foo" in msg
    assert "bar" in msg
```

Also update the import line near the top of `test_qwen_clone_tts.py`:

```python
from qwen_clone_tts import (LANG_CODES, MODEL_PATH, MOOD_PRESETS,
                            resolve_instruct, resolve_lang, _try_daemon,
                            split_mood_segments)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k split_mood_segments -v`
Expected: FAIL — `ImportError: cannot import name 'split_mood_segments'`

- [ ] **Step 3: Implement `split_mood_segments()`**

Insert into `qwen_clone_tts.py` right after the `chunk_text()` function
(after line 143, before `SOCK_PATH = ...`):

```python
_MOOD_TAG_RE = re.compile(r"\[mood:(\w+)\]")


def split_mood_segments(text: str) -> list[tuple[str | None, str]]:
    """แบ่งข้อความตาม [mood:xxx] tag คืน list ของ (mood_key, text_segment)

    mood_key เป็น None สำหรับเนื้อความก่อน tag แรก (ถ้ามี), lowercase เสมอ
    (ตรงกับ resolve_instruct() ที่ .lower() mood ก่อนเทียบ MOOD_PRESETS)
    ข้าม segment ที่ว่างเปล่าหลัง strip (เช่น tag ติดกันไม่มีเนื้อความคั่น)
    raise ValueError รวมทุก mood key ที่ไม่รู้จักในครั้งเดียว ก่อนคืนค่าใด ๆ
    (fail-fast — validate ทั้งไฟล์ก่อนเริ่ม generate ชิ้นแรก)
    """
    raw_tags = [m.lower() for m in _MOOD_TAG_RE.findall(text)]
    unknown = sorted(set(t for t in raw_tags if t not in MOOD_PRESETS))
    if unknown:
        raise ValueError(
            f"unknown mood(s) in --stdin tag: {', '.join(unknown)} — "
            f"choices: {', '.join(sorted(MOOD_PRESETS))}")

    parts = _MOOD_TAG_RE.split(text)
    segments: list[tuple[str | None, str]] = []
    pre = parts[0].strip()
    if pre:
        segments.append((None, pre))
    for i in range(1, len(parts), 2):
        key = parts[i].lower()
        seg_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if seg_text:
            segments.append((key, seg_text))
    return segments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k split_mood_segments -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add qwen_clone_tts.py test_qwen_clone_tts.py
git commit -m "feat(TTS-1012): add split_mood_segments() inline [mood:xxx] tag parser

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `_try_daemon()` — add `quiet` param

**Files:**
- Modify: `qwen_clone_tts.py:151-190`
- Test: `test_qwen_clone_tts.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `_try_daemon(text, out_path, instruct, voice="Liino", fmt="wav",
  lang="auto", quiet: bool = False) -> bool` — when `quiet=True`, suppresses the
  `OK <path>` / `TIMING ...` prints on success (still returns `True`/`False` and
  still prints `ERROR: daemon failed: ...` on daemon-side error). Existing call
  sites (`discord_say_bot.py:331`, `discord_say_bot.py:743`, `_run()`) pass no
  `quiet` and are unaffected — this is a trailing kwarg with a default.

- [ ] **Step 1: Write the failing tests**

Add to `test_qwen_clone_tts.py` after `test_try_daemon_leaves_absolute_out_path_unchanged`:

```python
def test_try_daemon_quiet_suppresses_stdout_and_stderr(monkeypatch, capsys):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    ok = _try_daemon("hi", "outputs/x.wav", None, quiet=True)

    assert ok is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_try_daemon_default_not_quiet_still_prints_ok(monkeypatch, capsys):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    ok = _try_daemon("hi", "outputs/x.wav", None)

    assert ok is True
    captured = capsys.readouterr()
    assert captured.out.startswith("OK ")
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k try_daemon_quiet -v`
Expected: FAIL — `TypeError: _try_daemon() got an unexpected keyword argument 'quiet'`

- [ ] **Step 3: Add the `quiet` param**

In `qwen_clone_tts.py`, change the signature and the success-print block
(`qwen_clone_tts.py:151-190`):

```python
def _try_daemon(text: str, out_path: str, instruct: str | None,
                voice: str = "Liino", fmt: str = "wav",
                lang: str = "auto", quiet: bool = False) -> bool:
    """ส่งงานผ่าน tts_daemon ถ้ารันอยู่ — คืน False ถ้า daemon ไม่พร้อม
    quiet=True ไม่ print OK/TIMING (ใช้เมื่อเป็นแค่ part หนึ่งของ multi-job
    dispatch ใน _run_multi() — ผลลัพธ์สุดท้ายที่ print คือหลัง concat เสร็จ)"""
    import json as _json
    import socket as _socket
    if not os.path.exists(SOCK_PATH):
        return False
    # daemon cwd ไม่ใช่ cwd ของผู้ใช้ (launchd = /) — ส่ง absolute path เสมอ
    # ให้ daemon เขียนไฟล์ที่เดียวกับที่ผู้ใช้ตั้งใจ
    out_path = os.path.abspath(out_path)
    try:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        # connect เร็ว (daemon ควรตอบทันทีว่าพร้อมหรือไม่) แต่รอผล gen ได้นาน
        sock.settimeout(DAEMON_CONNECT_TIMEOUT_S)
        sock.connect(SOCK_PATH)
        sock.sendall((_json.dumps(
            {"text": text, "instruct": instruct, "out_path": out_path,
             "voice": voice, "format": fmt, "lang": lang}) + "\n").encode("utf-8"))
        sock.settimeout(DAEMON_TIMEOUT_S)
        buf = b""
        while not buf.endswith(b"\n"):
            data = sock.recv(65536)
            if not data:
                break
            buf += data
        sock.close()
        resp = _json.loads(buf.decode("utf-8"))
    except (OSError, ValueError):
        return False
    if not resp.get("ok"):
        print(f"ERROR: daemon failed: {resp.get('error')}", file=sys.stderr)
        return False
    if not quiet:
        tag = " (cached)" if resp.get("cached") else ""
        print(f"OK {resp['out_path']}")
        qw = resp.get("queue_wait_s")
        qw_s = f" queue_wait={qw:.2f}s" if isinstance(qw, (int, float)) else ""
        print(f"TIMING via daemon gen={resp.get('gen_s', 0):.2f}s{qw_s}{tag}",
              file=sys.stderr)
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k try_daemon -v`
Expected: all `try_daemon` tests pass (existing 2 + new 2 = 4 passed)

- [ ] **Step 5: Commit**

```bash
git add qwen_clone_tts.py test_qwen_clone_tts.py
git commit -m "feat(TTS-1012): add quiet param to _try_daemon() for multi-job dispatch

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `_run_multi()` — generate N mood segments, concat with ffmpeg

**Files:**
- Modify: `qwen_clone_tts.py` — insert new function directly after `_run()`
  (currently ends `qwen_clone_tts.py:324`), before `def main() -> int:`
- Test: `test_qwen_clone_tts.py`

**Interfaces:**
- Consumes: `resolve_instruct(mood, instruct, voice_default) -> str | None`
  (`qwen_clone_tts.py:89`), `chunk_text(text, max_chars=MAX_CHARS) -> list[str]`
  (`qwen_clone_tts.py:115`), `_try_daemon(..., quiet=...)` from Task 2,
  `_convert_to_mp3(path) -> str` (`qwen_clone_tts.py:193`), `VOICES_DIR`,
  `MODEL_PATH` module constants.
- Produces: `_run_multi(voice: str, segments: list[tuple[str | None, str]],
  voice_default: str | None, out_path: str, mp3: bool = False,
  lang: str = "auto") -> int` — same return-code convention as `_run()` (`0` success,
  non-zero on error), same `OK <path>` / `ERROR: ...` / `TIMING ...` output contract.
  `main()` (Task 4) calls this when `len(segments) >= 2`.

Only the daemon-success and daemon-failure-mid-run paths get automated tests below —
the in-process (`mlx_audio`) fallback branch has **zero existing unit test coverage
anywhere in this codebase** for the equivalent code in `_run()` today (only manual
CLI validation, per `CLAUDE.md`: "No test suite, linter, or build step in this repo
— nothing to run beyond the scripts themselves"). This task keeps that same coverage
boundary rather than introducing a new one; the in-process branch is covered by
Task 4's manual `### Validation` step instead.

- [ ] **Step 1: Write the failing tests**

Add to `test_qwen_clone_tts.py`, after the `_FakeSock` class block (need `shutil` and
`subprocess` imported at top of the test file — add `import shutil` and
`import subprocess` next to the existing `import socket` line):

```python
def test_run_multi_sends_per_segment_instruct_via_daemon(monkeypatch, tmp_path):
    """_run_multi ต้องส่ง instruct ที่ต่างกันต่อ segment ผ่าน daemon
    (quiet=True ทุกครั้ง) แล้วเรียก ffmpeg concat ครั้งเดียวรวมทุก part"""
    sent_payloads = []

    class _SeqFakeSock:
        def __init__(self):
            self._replied = False

        def settimeout(self, _t):
            pass

        def connect(self, _p):
            pass

        def sendall(self, data):
            sent_payloads.append(json.loads(data.decode("utf-8").strip()))

        def recv(self, _n):
            if self._replied:
                return b""
            self._replied = True
            return (json.dumps(
                {"ok": True, "out_path": "/ignored.wav", "gen_s": 0.1}) + "\n"
            ).encode("utf-8")

        def close(self):
            pass

    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _SeqFakeSock())
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ffmpeg")

    concat_calls = []

    class _FakeCompleted:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        concat_calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    out_path = str(tmp_path / "out.wav")
    segments = [("excited", "Hello there"), ("sleepy", "Good night")]
    rc = qwen_clone_tts._run_multi("Liino", segments, None, out_path)

    assert rc == 0
    assert len(sent_payloads) == 2
    assert sent_payloads[0]["instruct"] == MOOD_PRESETS["excited"]
    assert sent_payloads[1]["instruct"] == MOOD_PRESETS["sleepy"]
    assert sent_payloads[0]["text"] == "Hello there"
    assert sent_payloads[1]["text"] == "Good night"
    assert len(concat_calls) == 1
    assert "concat" in concat_calls[0]


def test_run_multi_aborts_whole_run_if_daemon_fails_mid_job(monkeypatch, tmp_path):
    """job แรกสำเร็จผ่าน daemon, job ที่สองล้มเหลว -> ทั้งรันต้อง fail
    ไม่ยอมให้ ffmpeg concat ไฟล์บางส่วนออกมา"""
    call_count = {"n": 0}

    class _FlakySock:
        def settimeout(self, _t):
            pass

        def connect(self, _p):
            pass

        def sendall(self, data):
            pass

        def recv(self, _n):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (json.dumps(
                    {"ok": True, "out_path": "/x.wav", "gen_s": 0.1}) + "\n"
                ).encode("utf-8")
            return b""  # job ที่ 2 เป็นต้นไป: daemon หลุด/ไม่ตอบ

        def close(self):
            pass

    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FlakySock())
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ffmpeg")

    def fail_if_called(*a, **k):
        raise AssertionError("ffmpeg concat must not run after a job failure")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    out_path = str(tmp_path / "out.wav")
    segments = [("excited", "one"), ("sleepy", "two")]
    rc = qwen_clone_tts._run_multi("Liino", segments, None, out_path)

    assert rc == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k run_multi -v`
Expected: FAIL — `AttributeError: module 'qwen_clone_tts' has no attribute '_run_multi'`

- [ ] **Step 3: Implement `_run_multi()`**

Insert into `qwen_clone_tts.py` directly after `_run()` (after line 324), before
`def main() -> int:`:

```python
def _run_multi(voice: str, segments: list[tuple[str | None, str]],
               voice_default: str | None, out_path: str,
               mp3: bool = False, lang: str = "auto") -> int:
    """generate เสียงจากหลาย mood segment (2 ขึ้นไป) แล้ว concat เป็นไฟล์เดียว
    ด้วย ffmpeg — ใช้เมื่อ --stdin มี [mood:xxx] tag ทำให้แบ่งได้มากกว่า 1 segment
    แต่ละ segment ถูก chunk_text() ต่ออีกชั้นถ้ายาวเกิน MAX_CHARS
    job ใดล้มเหลว -> ทั้งรัน fail ทันที ไม่มีการเล่นเสียงบางส่วน"""
    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        print(f"ERROR: ref voice not found: {ref_audio}", file=sys.stderr)
        return 1

    jobs: list[tuple[str | None, str]] = []
    for mood_key, seg_text in segments:
        try:
            instruct = resolve_instruct(mood_key, None, voice_default)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        for chunk in chunk_text(seg_text):
            jobs.append((instruct, chunk))
    if not jobs:
        print("ERROR: no text content after mood-tag parsing", file=sys.stderr)
        return 1

    import shutil
    import subprocess
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not found for concat", file=sys.stderr)
        return 1

    tmpdir = tempfile.mkdtemp(prefix="qwen_clone_chunks_")
    part_paths: list[str] = []
    load_s = 0.0
    try:
        part0 = os.path.join(tmpdir, "part_000.wav")
        instruct0, text0 = jobs[0]
        t0 = time.time()
        use_daemon = _try_daemon(text0, part0, instruct0, voice, fmt="wav",
                                 lang=lang, quiet=True)
        t1 = time.time()
        if use_daemon:
            part_paths.append(part0)
            for i, (instruct, text) in enumerate(jobs[1:], start=1):
                part = os.path.join(tmpdir, f"part_{i:03d}.wav")
                if not _try_daemon(text, part, instruct, voice, fmt="wav",
                                   lang=lang, quiet=True):
                    print(f"ERROR: daemon failed on job {i} of {len(jobs)}",
                          file=sys.stderr)
                    return 1
                part_paths.append(part)
        else:
            from mlx_audio.tts.utils import load_model
            from mlx_audio.tts.generate import generate_audio
            ref_text = None
            txt_path = os.path.join(VOICES_DIR, f"{voice}.txt")
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    ref_text = f.read().strip()
            model = load_model(MODEL_PATH)
            load_s = time.time() - t0
            t1 = time.time()
            for i, (instruct, text) in enumerate(jobs):
                part = os.path.join(tmpdir, f"part_{i:03d}.wav")
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    generate_audio(model=model, text=text,
                                   ref_audio=ref_audio, ref_text=ref_text,
                                   instruct=instruct, lang_code=lang,
                                   output_path=part)
                if os.path.isdir(part):
                    cands = sorted(
                        (os.path.join(part, f) for f in os.listdir(part)
                         if f.endswith((".wav", ".mp3"))),
                        key=os.path.getmtime)
                    if not cands:
                        print(f"ERROR: no audio for job {i}", file=sys.stderr)
                        return 1
                    part = cands[-1]
                elif not os.path.exists(part):
                    print(f"ERROR: job {i} output missing", file=sys.stderr)
                    return 1
                part_paths.append(part)

        list_file = os.path.join(tmpdir, "list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in part_paths:
                f.write(f"file '{p}'\n")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        r = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", list_file,
             "-ar", "24000", "-ac", "1", out_path],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_path):
            print(f"ERROR: ffmpeg concat failed: {r.stderr}", file=sys.stderr)
            return 1
        gen_s = time.time() - t1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    final_out = out_path
    if mp3:
        final_out = _convert_to_mp3(out_path)
    print(f"OK {final_out}")
    print(f"TIMING load={load_s:.1f}s gen={gen_s:.1f}s jobs={len(jobs)}",
          file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -k run_multi -v`
Expected: 2 passed

- [ ] **Step 5: Run the full suite so far**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -v`
Expected: all passed, no regressions from Tasks 1-2

- [ ] **Step 6: Commit**

```bash
git add qwen_clone_tts.py test_qwen_clone_tts.py
git commit -m "feat(TTS-1012): add _run_multi() for multi-mood-segment generate+concat

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire `--stdin` dispatch + remove dead `multi` branch from `_run()`

**Files:**
- Modify: `qwen_clone_tts.py:212-235` (`_run()` — remove dead `multi` branch)
- Modify: `qwen_clone_tts.py:358-365` (`main()`'s `--stdin` branch)

**Interfaces:**
- Consumes: `split_mood_segments()` (Task 1), `_run_multi()` (Task 3), existing
  `_run()`, `resolve_instruct()`, `read_instruction()` (from `voice_store`).
- Produces: no new public interface — this is the wiring task. `main()`'s exit code
  / stdout / stderr contract is unchanged for untagged files (Global Constraints).

No automated test for `main()`'s branching exists anywhere in this codebase today
(the existing test suite only covers pure helper functions, never `main()` /
`sys.argv` dispatch) — this task is verified via the manual steps in Step 4 below,
consistent with that existing boundary.

- [ ] **Step 1: Simplify `_run()`  — remove the dead `multi` branch**

Replace `qwen_clone_tts.py:212-296` (the whole function through the end of the
`if multi: ... else:` block, i.e. up to and including line 315's blank line) with:

```python
def _run(voice: str, text: str, out_path: str, instruct: str | None,
         mp3: bool = False, lang: str = "auto") -> int:
    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        print(f"ERROR: ref voice not found: {ref_audio}", file=sys.stderr)
        return 1

    # ลอง daemon ก่อน (ไม่ต้องโหลดโมเดล) — ถ้าไม่รัน fallback โหลดเอง
    if _try_daemon(text, out_path, instruct, voice,
                   fmt="mp3" if mp3 else "wav", lang=lang):
        return 0

    if len(text) > MAX_CHARS:
        print(f"ERROR: text is {len(text)} chars — max is {MAX_CHARS} "
              f"(use multiple [mood:xxx] segments via --stdin to split "
              f"longer text)", file=sys.stderr)
        return 1

    ref_text = None
    txt_path = os.path.join(VOICES_DIR, f"{voice}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    model = load_model(MODEL_PATH)
    load_s = time.time() - t0

    t1 = time.time()
    generate_audio(model=model, text=text, ref_audio=ref_audio,
                   ref_text=ref_text, instruct=instruct, lang_code=lang,
                   output_path=out_path)
    # หาไฟล์ที่ mlx_audio เขียนจริง (บางครั้งต่อท้ายเลขนับ)
    if os.path.isdir(out_path):
        cands = sorted(
            (os.path.join(out_path, f) for f in os.listdir(out_path)
             if f.endswith((".wav", ".mp3"))),
            key=os.path.getmtime)
        if not cands:
            print("ERROR: no audio produced", file=sys.stderr)
            return 1
        final = cands[-1]
    elif os.path.exists(out_path):
        final = out_path
    else:
        print("ERROR: output missing", file=sys.stderr)
        return 1

    gen_s = time.time() - t1

    final_out = final
    if mp3:
        final_out = _convert_to_mp3(final)

    print(f"OK {final_out}")
    print(f"TIMING load={load_s:.1f}s gen={gen_s:.1f}s", file=sys.stderr)
    return 0
```

(This drops the now-unreachable `chunks = chunk_text(text)` line and the entire
`multi`/`if multi: ... else:` branching — `multi` was hardcoded `False` and never
executed. Behavior for every existing caller is identical: daemon tried first with
the full text, `MAX_CHARS` still hard-rejects oversized text in the in-process
fallback, single `generate_audio()` call, same `OK`/`ERROR`/`TIMING` output.)

- [ ] **Step 2: Verify no regression from the `_run()` simplification**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -v`
Expected: all passed (no test exercised the dead `multi` branch, so nothing should
change)

- [ ] **Step 3: Wire the `--stdin` branch dispatch**

Replace `qwen_clone_tts.py:358-365`:

```python
        from voice_store import read_instruction
        try:
            instruct = resolve_instruct(mood, None, read_instruction("Liino"))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        return _run("Liino", text, out_path, instruct,
                    mp3="--mp3" in rest, lang=lang)
```

with:

```python
        from voice_store import read_instruction
        voice_default = read_instruction("Liino")
        try:
            segments = split_mood_segments(text)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        if not segments:
            print("ERROR: no text content after mood-tag parsing",
                  file=sys.stderr)
            return 1
        if len(segments) == 1:
            # ไม่มี [mood:xxx] tag เลย (mood_key=None -> ใช้ --mood flag เดิม),
            # หรือมี tag เดียวคลุมทั้งไฟล์ -> job เดียว ไม่ต้อง concat
            mood_key, seg_text = segments[0]
            try:
                instruct = resolve_instruct(mood_key or mood, None, voice_default)
            except ValueError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            return _run("Liino", seg_text, out_path, instruct,
                        mp3="--mp3" in rest, lang=lang)
        return _run_multi("Liino", segments, voice_default, out_path,
                          mp3="--mp3" in rest, lang=lang)
```

- [ ] **Step 4: Manual validation**

```bash
# 1. ไม่มี tag เลย — ต้องได้ OK <path> เหมือนก่อนแก้ทุกอย่าง
printf "สวัสดีครับ ทดสอบ stdin ไม่มี mood tag" > /tmp/tts-1012-plain.txt
.venv/bin/python qwen_clone_tts.py --stdin /tmp/tts-1012-plain.txt outputs/tts-1012-plain.wav
# คาดหวัง: "OK outputs/tts-1012-plain.wav" ที่ stdout

# 2. tag เดียวคลุมทั้งไฟล์
printf "[mood:excited]โห! ทดสอบ mood tag เดียว น่าตื่นเต้นมาก" > /tmp/tts-1012-single-tag.txt
.venv/bin/python qwen_clone_tts.py --stdin /tmp/tts-1012-single-tag.txt outputs/tts-1012-single-tag.wav
# คาดหวัง: OK <path> — ฟังแล้วโทนตื่นเต้นตาม mood excited

# 3. หลาย tag สลับ mood — ต้องผ่าน _run_multi + ffmpeg concat
printf "[mood:excited]โหตื่นเต้นมาก! [mood:sleepy]แต่ตอนนี้ง่วงจัง อยากนอนแล้ว" \
  > /tmp/tts-1012-multi-tag.txt
.venv/bin/python qwen_clone_tts.py --stdin /tmp/tts-1012-multi-tag.txt outputs/tts-1012-multi-tag.wav
# คาดหวัง: OK <path>, TIMING มี "jobs=2", ฟังแล้วโทนเปลี่ยนจากตื่นเต้น -> ง่วงจริง

# 4. mood key พิมพ์ผิด — ต้อง fail ทั้งไฟล์ ไม่สร้างไฟล์ใด ๆ
printf "[mood:exicted]typo test" > /tmp/tts-1012-bad-tag.txt
.venv/bin/python qwen_clone_tts.py --stdin /tmp/tts-1012-bad-tag.txt outputs/tts-1012-bad.wav
# คาดหวัง: "ERROR: unknown mood(s) in --stdin tag: exicted — choices: ..." ที่ stderr,
# exit code != 0, outputs/tts-1012-bad.wav ไม่ถูกสร้าง

echo "exit code last command: $?"
ls outputs/tts-1012-bad.wav 2>&1  # ต้องไม่มีไฟล์นี้
```

- [ ] **Step 5: Commit**

```bash
git add qwen_clone_tts.py
git commit -m "feat(TTS-1012): wire --stdin dispatch to mood-tag segments; drop dead multi branch

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Docs — fix stale chunking claims, document `[mood:xxx]`

**Files:**
- Modify: `README.md`
- Modify: `README_HERMES.md` (only if it documents `--stdin` text format directly —
  check first; per `obsidian/kanban/context/kanban-flow.md` this file documents an
  external consumer's (Hermes) expectations and must stay accurate)
- Modify: `qwen_clone_tts.py:1-13` (module docstring)

**Interfaces:** none (docs only)

- [ ] **Step 1: Update the module docstring**

Replace `qwen_clone_tts.py:9-12`:

```python
Hermes command-provider mode:
    qwen_clone_tts.py --stdin <input_path> <output_path>
    (อ่านข้อความจากไฟล์ UTF-8, ข้อความยาวเกิน 300 ตัวอักษรจะถูกแบ่งเป็น chunk
     แล้วต่อเสียงเป็นไฟล์เดียว, ใช้เสียงโคลน Liino)
```

with:

```python
Hermes command-provider mode:
    qwen_clone_tts.py --stdin <input_path> <output_path>
    (อ่านข้อความจากไฟล์ UTF-8, ใช้เสียงโคลน Liino เสมอ. ข้อความเดี่ยว ๆ
     (ไม่มี [mood:xxx] tag) ยังจำกัดที่ 300 ตัวอักษรเหมือนเดิม (--text ก็เช่นกัน).
     ใส่ [mood:xxx] tag คั่นในเนื้อความเพื่อสลับโทนเสียงหลายท่อนในไฟล์เดียว —
     กรณีนี้แต่ละท่อนถูก generate แยกแล้วต่อกันด้วย ffmpeg โดยอัตโนมัติ,
     ไม่มีข้อจำกัดความยาวรวมทั้งไฟล์)
```

- [ ] **Step 2: Fix the contradictory chunking claims in README.md**

Read the current text around each of these lines (`rtk read -l none -n README.md`)
before editing — line numbers may have drifted since this plan was written:

1. The feature table row currently reading roughly:
   `| **Stdin/file mode** | Read text from a file, auto-chunk long text, output one audio file | ... |`
   → change `auto-chunk long text` to
   `switch mood mid-file via [mood:xxx] tags, output one audio file`.

2. The `--text` flag row (`**Max 300 characters** — longer text is rejected with an
   error.`) — leave as-is, still true for `--text`.

3. The `--stdin` section intro (`**File / stdin mode** (reads text from a file,
   auto-chunks it, ...)`) → change to
   `(reads text from a file, supports [mood:xxx] tags to switch mood mid-file, ...)`.
   Add a short example line showing tag usage, e.g.:
   ```bash
   python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav
   # input.txt may contain: [mood:excited]Hi there! [mood:sleepy]So tired now...
   ```

4. The daemon section's `**300-char limit**` bullet — this one is about the
   *daemon's own per-request* limit and stays accurate (each generate call, whether
   from `_run()` or a job inside `_run_multi()`, is still ≤300 chars); no change
   needed there.

5. The troubleshooting table row `text is N chars — max is 300` /
   `long-text auto-chunking is disabled` — update the tip column to:
   `Split with [mood:xxx] tags for --stdin, or split the text yourself for --text`.

- [ ] **Step 3: Check `README_HERMES.md` for the same stale claim**

Run: `rtk proxy grep -n "auto.chunk\|300\|stdin" README_HERMES.md`

If it describes `--stdin` as auto-chunking or silent on the 300-char limit, apply
the same correction as Step 2 (Hermes today sends untagged plain text per the
`### Context` section of `obsidian/kanban/tasks/TTS-1012.md`, so its existing
behavior doesn't change — only note that `[mood:xxx]` is now available if a future
Hermes revision wants to use it).

- [ ] **Step 4: Commit**

```bash
git add README.md README_HERMES.md qwen_clone_tts.py
git commit -m "docs(TTS-1012): document [mood:xxx] inline tag, fix stale auto-chunk claims

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Final full-suite validation

**Files:** none (validation only)

- [ ] **Step 1: Run the full automated test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (baseline was 110 passed as of TTS-1011 + this ticket's new
tests: 9 from Task 1 + 2 from Task 2 + 2 from Task 3 = 13 new, expect 123 passed)

- [ ] **Step 2: Re-run the four manual `--stdin` scenarios from Task 4 Step 4**

Confirm all four still behave as expected after Task 5's doc-only changes (docs
shouldn't affect runtime, but this is the cheapest final sanity check).

- [ ] **Step 3: Update the ticket's `### Validation` checklist**

Check off the completed items in `obsidian/kanban/tasks/TTS-1012.md`
`### Acceptance Criteria` and `### Validation` sections with the actual commands run
and their results (this happens as part of `/kanban move-review TTS-1012`, not a
code commit — no `git commit` step here).
