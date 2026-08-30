# `/say` Language Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a caller pin the TTS output language (`/say language:`, `qwen_clone_tts.py --lang`, daemon `lang` field) so text is not mispronounced in the wrong language — e.g. Japanese read with the wrong accent.

**Architecture:** Add one shared constant `LANG_CODES` + one validator `resolve_lang()` in `qwen_clone_tts.py` (the existing source-of-truth module). Thread a `lang` value from each entry point → `_try_daemon` JSON → daemon `handle_request` → `_generate` → `generate_audio(lang_code=...)`. Default `"auto"` everywhere so current behaviour (Thai, Hermes `--stdin`) is unchanged. The daemon cache key gains `lang` **only when it is not `"auto"`**, so every existing cached entry still hits.

**Tech Stack:** Python 3.10+, stdlib `argparse` + `socket` + `json`, `mlx-audio` (`generate_audio(lang_code=...)`), `discord.py` `app_commands`, `pytest`.

**Ticket:** `obsidian/kanban/tasks/TTS-1006.md`

## Global Constraints

- Python 3.10+ syntax (`str | None`). **Always run with `.venv/bin/python`**, never system `python3`.
- Comments/docstrings Thai; identifiers + user-facing/log strings match each file's existing style (Thai user-facing in `discord_say_bot.py`, `OK <path>` / `ERROR: ...` on CLI).
- No new pip dependency. stdlib `socket` + line-delimited JSON only for the daemon; keep the FIFO/blocking loop.
- Daemon request/response = one JSON object + `\n`. Adding a field is allowed; **must not break the existing `qwen_clone_tts.py` client** — a request without `lang` must behave exactly as today.
- New CLI flag / protocol field → update `README.md` (CLI Reference + Daemon Protocol + caching line) and `README_HERMES.md` where the `--stdin` contract is described.
- Cache-key change is explicitly scoped: **existing cache entries are NOT invalidated** (lang is appended to the key only when `lang != "auto"`).
- Valid language codes, verbatim (from `models/Qwen3-TTS-12Hz-1.7B-Base-8bit/config.json` → `talker_config.codec_language_id`, plus `auto`):
  `auto, chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish`
  **Thai is not supported by the model** — Thai text always runs through `auto`.
- Default language value everywhere: `"auto"`.
- Unknown language code → reject with a clear error (do not silently fall back).
- Tests live at repo root as `test_<module>.py`, run with `.venv/bin/python -m pytest -q` from repo root (pytest infra already added in TTS-1005).
- Commit prefixes: `feat(TTS-1006): ` / `test(TTS-1006): ` / `docs(TTS-1006): `, trailer:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
  ```
- Branch: `feature/TTS-1006` (create from `main`).

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `qwen_clone_tts.py` | source of truth for `LANG_CODES` + `resolve_lang()`; thread `lang` through `_run` / `_try_daemon` / argparse / `--stdin` | modify |
| `tts_daemon.py` | read `lang` from request, validate, include in cache key (non-auto only), pass `lang_code` to `generate_audio`, log it, document protocol | modify |
| `discord_say_bot.py` | `/say language:` choice option → pass to `_try_daemon` | modify |
| `test_qwen_clone_tts.py` | unit tests for `resolve_lang()` + `LANG_CODES` sanity | create |
| `test_tts_daemon.py` | unit tests for `_cache_key` lang behaviour (backward compat + separation) | create |
| `README.md` | CLI Reference flag, `--stdin` example, Daemon caching line, Protocol JSON + code list, `/say` behaviour bullet | modify |
| `README_HERMES.md` | `--stdin` line + one note that `--lang` is optional (default `auto`) | modify |

---

### Task 1: `LANG_CODES` + `resolve_lang()` + thread `lang` through `qwen_clone_tts.py`

**Files:**
- Modify: `qwen_clone_tts.py` — add constants after `MOOD_PRESETS` (~line 68); `_try_daemon` (line 127-141); `_run` (line 184, 232, 268); `main()` argparse + `--stdin` block (line 298-352); module docstring line 6
- Test: `test_qwen_clone_tts.py` (create)

**Interfaces:**
- Produces:
  - `qwen_clone_tts.LANG_CODES: tuple[str, ...]` — `("auto", "chinese", "english", "french", "german", "italian", "japanese", "korean", "portuguese", "russian", "spanish")`. Consumed by Task 2 (daemon validation) and Task 3 (`/say` choices).
  - `qwen_clone_tts.resolve_lang(lang: str | None) -> str` — `None`/`""` → `"auto"`; lowercases + strips; raises `ValueError` if the result is not in `LANG_CODES`; else returns it. Consumed by Task 2.
  - `_try_daemon(text, out_path, instruct, voice="Liino", fmt="wav", lang="auto")` — adds `"lang": lang` to the request JSON.
  - `_run(voice, text, out_path, instruct, mp3=False, lang="auto")` — forwards `lang` to `_try_daemon` and passes `lang_code=lang` to `generate_audio(...)` in the fallback path.

- [ ] **Step 1: Write the failing tests**

Create `test_qwen_clone_tts.py`:

```python
"""Unit test สำหรับ qwen_clone_tts language resolution (TTS-1006)"""
import json
import os

import pytest

from qwen_clone_tts import LANG_CODES, MODEL_PATH, resolve_lang


def test_resolve_lang_none_is_auto():
    assert resolve_lang(None) == "auto"


def test_resolve_lang_empty_is_auto():
    assert resolve_lang("") == "auto"


def test_resolve_lang_lowercases_and_strips():
    assert resolve_lang("  Japanese ") == "japanese"


def test_resolve_lang_passthrough_valid():
    assert resolve_lang("english") == "english"


def test_resolve_lang_rejects_unknown():
    with pytest.raises(ValueError):
        resolve_lang("thai")


def test_lang_codes_has_auto_first_and_is_sorted_rest():
    assert LANG_CODES[0] == "auto"
    assert list(LANG_CODES[1:]) == sorted(LANG_CODES[1:])


@pytest.mark.skipif(
    not os.path.isfile(os.path.join(MODEL_PATH, "config.json")),
    reason="model config not present")
def test_lang_codes_match_model_config():
    cfg = json.load(open(os.path.join(MODEL_PATH, "config.json")))
    model_langs = set(
        cfg["talker_config"]["codec_language_id"].keys())
    assert set(LANG_CODES) - {"auto"} == model_langs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -q`
Expected: FAIL — `ImportError: cannot import name 'LANG_CODES' from 'qwen_clone_tts'`

- [ ] **Step 3: Add `LANG_CODES` + `resolve_lang()`**

In `qwen_clone_tts.py`, immediately after the `MOOD_PRESETS` dict closes (currently line 67), add:

```python


# ภาษาที่ Qwen3-TTS-12Hz รองรับ — ดึงจาก config.json ของโมเดล
# (talker_config.codec_language_id) + "auto" (ให้โมเดลเดาจากข้อความ)
# หมายเหตุ: โมเดลไม่รองรับภาษาไทย — ข้อความไทยใช้ "auto" เท่านั้น
LANG_CODES: tuple[str, ...] = (
    "auto", "chinese", "english", "french", "german", "italian",
    "japanese", "korean", "portuguese", "russian", "spanish",
)


def resolve_lang(lang: str | None) -> str:
    """normalize + validate language code — คืน "auto" ถ้าไม่ระบุ

    lowercase + strip; ไม่อยู่ใน LANG_CODES -> ValueError (caller แปลงเป็น
    ERROR: / ephemeral). ปล่อยผ่านเงียบ ๆ ไม่ได้ เพราะ lang ผิดจะออกเสียงเพี้ยน
    """
    if not lang:
        return "auto"
    code = lang.strip().lower()
    if code not in LANG_CODES:
        raise ValueError(
            f"unknown lang '{code}' — choices: {', '.join(LANG_CODES)}")
    return code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_qwen_clone_tts.py -q`
Expected: PASS — 7 tests green (or 6 + 1 skipped if the model dir is absent).

- [ ] **Step 5: Thread `lang` through `_try_daemon` and `_run`**

In `qwen_clone_tts.py`:

Change `_try_daemon` signature + request dict (lines 127-141):

```python
def _try_daemon(text: str, out_path: str, instruct: str | None,
                voice: str = "Liino", fmt: str = "wav",
                lang: str = "auto") -> bool:
    """ส่งงานผ่าน tts_daemon ถ้ารันอยู่ — คืน False ถ้า daemon ไม่พร้อม"""
    import json as _json
    import socket as _socket
    if not os.path.exists(SOCK_PATH):
        return False
    try:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        sock.settimeout(DAEMON_CONNECT_TIMEOUT_S)
        sock.connect(SOCK_PATH)
        sock.sendall((_json.dumps(
            {"text": text, "instruct": instruct, "out_path": out_path,
             "voice": voice, "format": fmt, "lang": lang}) + "\n").encode("utf-8"))
```

Change `_run` signature (line 184) and both `generate_audio` calls + the `_try_daemon` call:

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
```

In the `multi` branch (line 232-234):

```python
                    generate_audio(model=model, text=chunk,
                                   ref_audio=ref_audio, ref_text=ref_text,
                                   instruct=instruct, lang_code=lang,
                                   output_path=part)
```

In the single branch (line 268-270):

```python
        generate_audio(model=model, text=text, ref_audio=ref_audio,
                       ref_text=ref_text, instruct=instruct, lang_code=lang,
                       output_path=out_path)
```

- [ ] **Step 6: Add `--lang` to argparse and `--stdin` mode**

In `main()` — `--stdin` block (after the `--mood` parsing, ~line 320, before `resolve_instruct`):

```python
        lang = "auto"
        if "--lang" in rest:
            i = rest.index("--lang")
            lang = rest[i + 1] if i + 1 < len(rest) else "auto"
            rest = rest[:i] + rest[i + 2:]
        try:
            lang = resolve_lang(lang)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        try:
            instruct = resolve_instruct(mood, None,
                                        "--instruct-long" in rest)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        return _run("Liino", text, out_path, instruct,
                    mp3="--mp3" in rest, lang=lang)
```

In the argparse section (after the `--mood` arg, ~line 342):

```python
    ap.add_argument("--lang", default="auto", choices=LANG_CODES,
                    help="ภาษาที่โมเดลออกเสียง (default auto = เดาจากข้อความ; "
                         "ภาษาไทยใช้ auto)")
```

And the final call (line 352):

```python
    return _run(args.voice, args.text, out_path, instruct, mp3=args.mp3,
                lang=args.lang)
```

- [ ] **Step 7: Update the module docstring**

Change line 6 from `[--instruct "คำบรรยายน้ำเสียง"] [--lang th|en|...]` to:

```
                      [--instruct "คำบรรยายน้ำเสียง"]
                      [--lang auto|japanese|english|chinese|...]
```

- [ ] **Step 8: Run the full suite + a manual smoke**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — full suite green (TTS-1005 tests + new `test_qwen_clone_tts.py`).

Run: `.venv/bin/python -c "import qwen_clone_tts, tts_daemon, discord_say_bot; print('imports OK')"`
Expected: `imports OK` (nothing broke downstream importers yet — daemon/bot still call the old-arity functions with defaults).

- [ ] **Step 9: Commit**

```bash
git add qwen_clone_tts.py test_qwen_clone_tts.py
git commit -m "$(cat <<'EOF'
feat(TTS-1006): Add LANG_CODES + resolve_lang, thread lang through CLI

New shared constant LANG_CODES (from model config codec_language_id + auto)
and resolve_lang() validator. --lang flag on both --text and --stdin modes,
plumbed to _try_daemon (new "lang" request field) and generate_audio
(lang_code=). Default "auto" everywhere. Thai is unsupported by the model
and always uses auto.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 2: `tts_daemon.py` — read/validate `lang`, cache key, `generate_audio`, telemetry, protocol doc

**Files:**
- Modify: `tts_daemon.py` — import (line 44-45); `_cache_key` (line 91-94); `_generate` (line 157-158, 181-183, 210-212); `handle_request` (line 240-244, 255-256, 288, 311-312); module docstring (line 4-9)
- Test: `test_tts_daemon.py` (create)

**Interfaces:**
- Consumes: `qwen_clone_tts.LANG_CODES` (Task 1).
- Produces:
  - `tts_daemon._cache_key(text, instruct, voice, lang="auto") -> str` — hash of `f"{voice}\x00{text}\x00{instruct or ''}"`, with `f"\x00{lang}"` appended **only when `lang` is truthy and not `"auto"`**. So `lang="auto"` and a missing `lang` both produce the pre-TTS-1006 hash → existing cache entries keep hitting.
  - `tts_daemon._generate(model_holder, ref_audio, ref_text, text, instruct, out_path, lang="auto") -> float` — passes `lang_code=lang` to `generate_audio`.
  - `handle_request` — reads `req.get("lang", "auto")`; on an unknown code returns an `ok: false` response with `error` `"unknown lang '<x>' — choices: ..."`.

- [ ] **Step 1: Write the failing tests**

Create `test_tts_daemon.py`:

```python
"""Unit test สำหรับ tts_daemon cache key + lang (TTS-1006)"""
from tts_daemon import _cache_key


def test_cache_key_auto_equals_legacy_no_lang():
    # request เดิม (ไม่มี lang) ต้อง hash เท่ากับ lang="auto" -> cache เดิมยัง hit
    legacy = _cache_key("สวัสดี", None, "Liino")
    explicit_auto = _cache_key("สวัสดี", None, "Liino", "auto")
    assert legacy == explicit_auto


def test_cache_key_non_auto_differs():
    auto = _cache_key("hello", None, "Liino", "auto")
    ja = _cache_key("hello", None, "Liino", "japanese")
    en = _cache_key("hello", None, "Liino", "english")
    assert len({auto, ja, en}) == 3


def test_cache_key_stable_for_same_inputs():
    assert _cache_key("x", "instruct", "Liino", "korean") == \
        _cache_key("x", "instruct", "Liino", "korean")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest test_tts_daemon.py -q`
Expected: FAIL — `TypeError: _cache_key() takes 3 positional arguments but 4 were given`

- [ ] **Step 3: Update `_cache_key`**

In `tts_daemon.py`, replace `_cache_key` (lines 91-94):

```python
def _cache_key(text: str, instruct: str | None, voice: str,
               lang: str = "auto") -> str:
    h = hashlib.sha256()
    base = f"{voice}\x00{text}\x00{instruct or ''}"
    # lang เพิ่มเข้า key เฉพาะเมื่อไม่ใช่ auto — cache ที่มีอยู่ก่อน TTS-1006
    # (ทั้งหมดคือ auto โดยปริยาย) จึงยัง hit ได้ ไม่ invalidate
    if lang and lang != "auto":
        base += f"\x00{lang}"
    h.update(base.encode("utf-8"))
    return h.hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest test_tts_daemon.py -q`
Expected: PASS — 3 tests green.

- [ ] **Step 5: Thread `lang` through `_generate` and `handle_request`**

In `tts_daemon.py`:

Add to the project import (line 44-45):

```python
from qwen_clone_tts import (  # noqa: E402
    DEFAULT_INSTRUCT, LANG_CODES, MAX_CHARS, MODEL_PATH, VOICES_DIR, chunk_text)
```

`_generate` signature (line 157-158):

```python
def _generate(model_holder, ref_audio: str, ref_text: str | None, text: str,
              instruct: str | None, out_path: str, lang: str = "auto") -> float:
```

Both `generate_audio(...)` calls inside `_generate` (line 181-183 and 210-212) gain `lang_code=lang`:

```python
                    generate_audio(model=model, text=chunk,
                                   ref_audio=ref_audio, ref_text=ref_text,
                                   instruct=instruct, lang_code=lang,
                                   output_path=part)
```

```python
                generate_audio(model=model, text=text, ref_audio=ref_audio,
                               ref_text=ref_text, instruct=instruct,
                               lang_code=lang, output_path=out_path)
```

In `handle_request`, after `fmt` is resolved (line 244-246):

```python
    fmt = req.get("format", "wav")
    if fmt not in ("wav", "mp3"):
        fmt = "wav"
    lang = req.get("lang", "auto")
    if lang not in LANG_CODES:
        return {"ok": False, "out_path": out_path or "", "gen_s": 0.0,
                "error": f"unknown lang '{lang}' — choices: "
                         f"{', '.join(LANG_CODES)}",
                "cached": False, "queue_wait_s": round(queue_wait_s, 2),
                "format": fmt}
```

Add `lang` to the request telemetry (line 255-256):

```python
    log_event("request", text_len=len(text), lang=lang,
              queue_wait_s=round(queue_wait_s, 2))
```

Use `lang` in the cache key (line 288):

```python
    key = _cache_key(text, instruct, voice, lang)
```

Pass `lang` to `_generate` (line 311-312):

```python
        gen_s = _generate(model_holder, ref_audio, ref_text, text, instruct,
                          gen_path, lang)
```

- [ ] **Step 6: Update the module docstring protocol block**

Replace lines 4-9:

```
Protocol (JSON บรรทัดเดียว จบด้วย newline):
    request : {"text": str, "instruct": str|null, "out_path": str, "voice": str?,
               "format": "wav"|"mp3"?, "lang": str?}
               lang = "auto" (default) หรือ code ที่โมเดลรองรับ
               (japanese, english, chinese, ...) — ดู qwen_clone_tts.LANG_CODES;
               ไม่ส่ง lang = "auto" (backward compatible)
    response: {"ok": bool, "out_path": str, "gen_s": float,
               "error": str|null, "cached": bool, "queue_wait_s": float,
               "format": "wav"|"mp3"}
```

- [ ] **Step 7: Run tests + a live daemon round-trip**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — full suite green.

Run (needs the model; ~1 min):

```bash
.venv/bin/python tts_daemon.py &
sleep 8
# request WITHOUT lang — must still work (backward compat) and hit legacy cache
printf '{"text":"สวัสดีค่ะ วันนี้อากาศดี","instruct":null,"out_path":"/tmp/t_th.wav","voice":"Liino","format":"wav"}\n' | nc -U /tmp/qwen_tts_daemon.sock
# request WITH lang
printf '{"text":"こんにちは、元気ですか","instruct":null,"out_path":"/tmp/t_ja.wav","voice":"Liino","format":"wav","lang":"japanese"}\n' | nc -U /tmp/qwen_tts_daemon.sock
# request with a bad code — must return ok:false, not crash
printf '{"text":"x","instruct":null,"out_path":"/tmp/t_x.wav","voice":"Liino","lang":"thai"}\n' | nc -U /tmp/qwen_tts_daemon.sock
kill %1
```

Expected: first two `"ok": true`; third `"ok": false` with `"unknown lang 'thai'"`. `TTS_TELEMETRY_LOG` shows `"lang"` on the request lines. `~/.cache/qwen_tts` has a new file for the `japanese` request keyed differently from any `auto` entry.

- [ ] **Step 8: Commit**

```bash
git add tts_daemon.py test_tts_daemon.py
git commit -m "$(cat <<'EOF'
feat(TTS-1006): Daemon honours request "lang", cache-key stays compatible

handle_request reads req["lang"] (default "auto"), rejects unknown codes,
passes lang_code to generate_audio, logs it. _cache_key appends lang only
when it is not "auto" so every pre-TTS-1006 cache entry still hits.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 3: `discord_say_bot.py` — `/say language:` option

**Files:**
- Modify: `discord_say_bot.py` — project import (line 42); `say` command decorators + signature (line 167-178); the `_try_daemon` call (line 280-281); telemetry line (line 310-313)
- Test: none automated (Discord runtime) — covered by manual validation

**Interfaces:**
- Consumes: `qwen_clone_tts.LANG_CODES` (Task 1); the `lang=` kwarg of `_try_daemon` (Task 1).

- [ ] **Step 1: Import `LANG_CODES`**

Change line 42:

```python
from qwen_clone_tts import LANG_CODES, MAX_CHARS, MOOD_PRESETS, _try_daemon, resolve_instruct  # noqa: E402
```

- [ ] **Step 2: Add the `language` option to `/say`**

Replace the `say` decorators + signature (lines 167-178):

```python
@tree.command(name="say",
              description="ให้บอทพูดข้อความใน voice channel ด้วยเสียง Liino")
@app_commands.guild_only()
@app_commands.describe(
    text="ข้อความบรรทัดเดียว (หลายบรรทัดให้ใช้ file:)",
    mood="โทนเสียง (ไม่เลือก = auto จาก emoji หรือปกติ)",
    language="ภาษาที่โมเดลออกเสียง (ไม่เลือก = auto เดาจากข้อความ; ไทยใช้ auto)",
    file="ไฟล์ .txt สำหรับข้อความหลายบรรทัด (1 บรรทัด = 1 ประโยค, UTF-8, ≤100 KB)")
@app_commands.choices(
    mood=[app_commands.Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)],
    language=[app_commands.Choice(name=c, value=c)
              for c in LANG_CODES if c != "auto"])
async def say(interaction: discord.Interaction, text: str | None = None,
              mood: str | None = None,
              language: str | None = None,
              file: discord.Attachment | None = None) -> None:
    explicit_mood = mood  # ชื่อ preset ที่เลือกจาก dropdown หรือ None
    lang = language or "auto"  # ไม่เลือก = auto (choice list ไม่มี auto)
```

- [ ] **Step 3: Pass `lang` to `_try_daemon`**

Change the generate call (line 280-281):

```python
        ok = await asyncio.to_thread(
            _try_daemon, spoken, wav_path, instruct, DEFAULT_VOICE, "wav", lang)
```

- [ ] **Step 4: Add `lang` to the telemetry line**

Change the success `print(...)` (line 310-313):

```python
    print(f"discord_say_bot: queued say guild={interaction.guild.id} "
          f"src={src} lines={len(wav_paths)} gen_s={gen_s:.2f} "
          f"explicit_mood={explicit_mood} lang={lang} chars={total_chars}",
          file=sys.stderr, flush=True)
```

- [ ] **Step 5: Import + suite check**

Run: `.venv/bin/python -c "import discord_say_bot; print('import OK')"`
Expected: `import OK` (command re-registers on the tree with the new option).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — no regression.

- [ ] **Step 6: Commit**

```bash
git add discord_say_bot.py
git commit -m "$(cat <<'EOF'
feat(TTS-1006): Add /say language: option

Optional language: choice (model codes, unset = auto) forwarded to
_try_daemon so a Discord user can pin the TTS output language.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

---

### Task 4: Documentation — `README.md` + `README_HERMES.md`

**Files:**
- Modify: `README.md` — CLI Reference flag table (~line 161), `--stdin` examples (~line 168), Daemon "Response caching" bullet (line 191), Protocol JSON block (line 211-217), `/say` behaviour list (~line 261)
- Modify: `README_HERMES.md` — `--stdin` description line (line 28), CLI example block (~line 132)
- Test: none (docs)

- [ ] **Step 1: CLI Reference — `--lang` row**

In the flag table, add after the `--instruct-long` row (line 161):

```markdown
| `--lang CODE` | no (default `auto`) | Output language for the TTS model. `auto` lets the model infer it from the text. Valid: `auto, chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish`. **Thai is not a model language — Thai text uses `auto`.** |
```

- [ ] **Step 2: CLI Reference — `--stdin` example**

In the `--stdin` code block (after line 168), add:

```bash
python qwen_clone_tts.py --stdin path/to/input.ja.txt out.wav --lang japanese
```

- [ ] **Step 3: Daemon "Response caching" bullet**

Change line 191:

```markdown
- **Response caching** — identical `(voice, text, instruct, lang)` requests return a cached file instantly (`cached: true` in the response), even after the model has been idle-unloaded. A request with no `lang` (or `lang: "auto"`) uses the same cache key it always did, so upgrading the daemon does not invalidate the existing cache.
```

- [ ] **Step 4: Protocol JSON block**

Replace lines 211-217:

```json
// request
{"text": "hello", "instruct": null, "out_path": "/tmp/out.wav", "voice": "Liino", "format": "wav", "lang": "auto"}

// response
{"ok": true, "out_path": "/tmp/out.wav", "gen_s": 3.2, "error": null, "cached": false, "queue_wait_s": 0.01, "format": "wav"}
```

And add a sentence right after the code block (before "The `qwen_clone_tts.py` client already implements this protocol"):

```markdown
`lang` is optional and defaults to `"auto"` (omitting it is identical to sending `"auto"`). Valid values are `auto` plus the model's language codes: `chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish`. An unknown code returns `ok: false`.
```

- [ ] **Step 5: `/say` behaviour list**

In §Discord Bot behaviour list, add a bullet after the `mood:<preset>` bullet (line 261):

```markdown
- **`language:<code>`** — pin the TTS output language (`japanese`, `english`, `chinese`, …) so text isn't mispronounced in the wrong language. Leave it unset for `auto` (the model infers language from the text; Thai always uses `auto`). Applies to every line of a `text:` or `file:` request.
```

- [ ] **Step 6: `README_HERMES.md`**

Line 28 — append to the `qwen_clone_tts.py` row:

```markdown
| `qwen_clone_tts.py` | CLI สร้างเสียง; โหมด `--stdin <in> <out>` ใช้กับ Hermes; แบ่งข้อความเป็น chunk ≤300 ตัวอักษรแล้วต่อเสียง; `--lang <code>` optional (default `auto`, Hermes ไม่ต้องส่ง) |
```

In the CLI example block (~line 132), add a comment line:

```bash
# ระบุภาษา (ไม่บังคับ — default auto): --lang japanese
```

- [ ] **Step 7: Commit**

```bash
git add README.md README_HERMES.md
git commit -m "$(cat <<'EOF'
docs(TTS-1006): Document --lang / request lang field / /say language:

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015DQZok6qkXG5Hs7apbb5Lm
EOF
)"
```

- [ ] **Step 8: Manual / live validation** (record in the ticket's Review Notes)

Prereqs: `.venv/bin/python tts_daemon.py` running; for the Discord checks, `DISCORD_BOT_TOKEN` exported and `.venv/bin/python discord_say_bot.py` running.

1. **CLI Japanese:** `.venv/bin/python qwen_clone_tts.py --text "こんにちは、元気ですか" --lang japanese --out outputs/ja.wav` → `OK ...`; listen — Japanese pronunciation. Compare with `--lang auto`.
2. **CLI Thai regression:** `.venv/bin/python qwen_clone_tts.py --text "สวัสดีค่ะ วันนี้อากาศดีมาก" --out outputs/th.wav` (no `--lang`) → `OK ...`; listen — Thai unchanged from before.
3. **CLI bad code:** `.venv/bin/python qwen_clone_tts.py --text "x" --lang thai` → exits non-zero, `ERROR: unknown lang 'thai' — choices: ...`, argparse rejects it before run.
4. **`--stdin` + `--lang`:** `printf 'こんにちは' > /tmp/j.txt && .venv/bin/python qwen_clone_tts.py --stdin /tmp/j.txt /tmp/j.wav --lang japanese` → `OK /tmp/j.wav`.
5. **`--stdin` no `--lang` (Hermes path):** same without `--lang` → `OK` (default auto, unchanged).
6. **Daemon backward compat:** send a raw request with no `lang` key (see Task 2 Step 7) → `ok: true`; if that exact `(voice,text,instruct)` was cached before the upgrade, `cached: true`.
7. **Daemon cache separation:** same text via `/say` once with `language:japanese`, once with `language:english` → `~/.cache/qwen_tts` gains two distinct files; second call of each is `cached: true`.
8. **Discord:** `/say text:"こんにちは" language:japanese` → Liino speaks Japanese. `/say text:"สวัสดี"` (no language) → Thai, unchanged.
9. **Round-trip:** `/transcribe` a Japanese clip → `.txt` → `/say file:` with `language:japanese` → each line spoken in Japanese with the emoji mood.

---

## Self-Review

**1. Spec coverage (ticket TTS-1006):**

| Ticket item | Task |
|---|---|
| Scope: `qwen_clone_tts.py` `--lang` (both modes), `_run`/`_try_daemon` plumbing, `generate_audio(lang_code=)` | Task 1 |
| Scope: `tts_daemon.py` `handle_request` reads `lang`, `_generate`, `_cache_key`, telemetry, docstring | Task 2 |
| Scope: `discord_say_bot.py` `/say language:` choices → `_try_daemon` | Task 3 |
| Scope: `README.md` Protocol / Discord Bot / CLI Reference; `README_HERMES.md` | Task 4 |
| AC: `/say language:japanese` → correct Japanese | Task 3 + Task 4 Step 8.8 |
| AC: `--lang japanese` CLI works | Task 1 + Task 4 Step 8.1 |
| AC: daemon `lang` optional, missing → `auto`, no regression | Task 2 Step 5 + Step 7 + Step 8.6 |
| AC: cache key separates by lang | Task 2 Step 3 + test + Step 8.7 |
| AC: pre-TTS-1006 cache still hits | Task 2 `_cache_key` (append only when non-auto) + `test_cache_key_auto_equals_legacy_no_lang` |
| AC: Hermes `--stdin` not broken | Task 1 Step 6 + Task 4 Step 8.5 |
| AC: `/say` without `language:` → auto, Thai unchanged | Task 3 Step 2 + Task 4 Step 8.2 / 8.8 |
| AC: README + HERMES + daemon docstring updated | Task 2 Step 6 + Task 4 |
| OQ1: `/say` choices = model codes, unset = auto | Task 3 Step 2 (`if c != "auto"`) |
| OQ2: default `auto` everywhere | Task 1 (all signatures), Task 2, Task 3 |
| OQ3: cache key `lang or "auto"`, no invalidation | Task 2 Step 3 |
| OQ4: unknown lang → reject | Task 1 `resolve_lang` (CLI), Task 2 `handle_request` (daemon) |
| OQ5: `--lang` on `--text` and `--stdin` | Task 1 Step 6 |

No gaps.

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". Every code step has full code; every table row and doc string is verbatim.

**3. Type consistency:**
- `LANG_CODES: tuple[str, ...]` — defined Task 1, imported Task 2 (`lang not in LANG_CODES`) and Task 3 (choice list). Consistent.
- `resolve_lang(lang: str | None) -> str` — defined Task 1, used Task 1 `--stdin`. (Daemon does its own inline `lang not in LANG_CODES` check rather than calling `resolve_lang`, because it must return a JSON error response, not raise — noted in Task 2 interfaces.) Consistent.
- `_try_daemon(..., lang: str = "auto")` — defined Task 1, called Task 3 positionally as the 6th arg (`..., "wav", lang`). Matches the signature order `text, out_path, instruct, voice, fmt, lang`. Consistent.
- `_run(..., lang: str = "auto")` — defined Task 1, called Task 1 `main()` both modes. Consistent.
- `_generate(..., lang: str = "auto") -> float` — defined Task 2, called Task 2 `handle_request` positionally as 7th arg. Consistent.
- `_cache_key(text, instruct, voice, lang="auto")` — defined Task 2, called Task 2 `handle_request` as `_cache_key(text, instruct, voice, lang)`. Consistent.

No issues found.

**4. Risk notes for the reviewer:**
- Today every `generate_audio` call in this repo omits `lang_code`, so mlx-audio's default `"en"` is in effect. After this change the default becomes `"auto"`. For Thai/Japanese this is neutral-to-better (Thai isn't a model code → same fallback path either way; `"auto"` lets the model detect). Existing daemon cache entries were generated under `"en"` but keep their key and will be served for new `"auto"` requests — acceptable (cache is opportunistic; en≈auto for non-listed languages). Validated by Step 8.2 (Thai regression) and 8.6.
- `--stdin` arg parsing is hand-rolled; `--lang <val>` removes two tokens exactly like `--mood` — verify `--lang` at the end of argv (no value) degrades to `"auto"` (Step 6 guards `i + 1 < len(rest)`).
