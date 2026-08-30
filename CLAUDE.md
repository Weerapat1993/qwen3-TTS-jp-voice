# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local Qwen3-TTS (voice-clone/design/custom-voice) runner for Apple Silicon using MLX — no cloud. Two entry points with different audiences:

- `main.py` — interactive human menu (model select → mode → prompts). Not scriptable.
- `qwen_clone_tts.py` — non-interactive CLI, flag-based, no prompts. **This is the one to use/extend for scripting or agent integration.**

The primary real-world consumer is a Hermes agent (separate project) that shells out to `qwen_clone_tts.py --stdin <input.txt> <output.wav>` as a TTS provider using a cloned voice called "Liino". See `README_HERMES.md` for that integration's full details (Thai) — read it before touching anything that affects the `--stdin` path or the daemon protocol, since it documents an external consumer's expectations.

## Setup / running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg
```

Requires Python 3.10+ (code uses `str | None` syntax). **Never use system `python3`** — if it's <3.10 the CLI fails silently-ish with `TTS chunk 1 produced no final audio`. Always use `.venv/bin/python`.

Models go in `models/<name>/` (downloaded separately from HuggingFace `mlx-community/Qwen3-TTS-12Hz-*`, not in git — see `.gitignore`). Voice clone reference clips go in `voices/<Name>.wav` (+ optional `voices/<Name>.txt` transcript to improve cloning).

```bash
# interactive menu
python main.py

# scripted single call
python qwen_clone_tts.py --text "Hello" --voice Liino --instruct "cheerful voice" --out outputs/x.wav [--mp3]

# Hermes-style stdin/file mode (auto-chunks, always voice=Liino)
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav [--mp3] [--mood excited]

# background daemon (loads model once, serves over Unix socket)
.venv/bin/python tts_daemon.py
```

No test suite, linter, or build step in this repo — nothing to run beyond the scripts themselves. `tune_voice.py` is an ad-hoc A/B tuning script (not a test), it generates sample audio across instruct/ref-audio variants into `outputs/tuning/<run_id>/` with a `results.md` summary.

## Architecture

**Everything funnels through `mlx_audio.tts.generate.generate_audio()` + `mlx_audio.tts.utils.load_model()`** (external `mlx-audio` package, pinned as a git dependency in requirements.txt). All three scripts (`main.py`, `qwen_clone_tts.py`, `tune_voice.py`, `tts_daemon.py`) call these the same way; `qwen_clone_tts.py` is the shared source of truth for constants (`MODEL_PATH`, `VOICES_DIR`, `MAX_CHARS`, mood/instruct presets, `chunk_text()`) — `tts_daemon.py`, `tune_voice.py`, and `voice_store.py` (imports `VOICES_DIR`) import from it rather than duplicating. `discord_say_bot.py` imports `voice_store` for the `/voice-clone` command group (voice-file CRUD + reference-audio prep — a pure module with no `discord` import, unit-tested via `test_voice_store.py`).

**Two ways `qwen_clone_tts.py` produces audio, decided at runtime:**
1. If `/tmp/qwen_tts_daemon.sock` exists → send a JSON request to `tts_daemon.py` (fast path, no model load).
2. Otherwise → load the model in-process itself (slow path, ~3-10s load).

This fallback logic lives in `_try_daemon()` / `_run()` in `qwen_clone_tts.py`. When changing the request/response shape, update both sides — `tts_daemon.py`'s `handle_request()` and `qwen_clone_tts.py`'s `_try_daemon()` — they hand-implement the same JSON-line-over-Unix-socket protocol (documented in the daemon's module docstring and in `README.md` § Protocol).

**`tts_daemon.py` internals** (the part most likely to need care when changing):
- Single worker thread pulls a FIFO `queue.Queue`; jobs are atomic — a running generation is never cancelled, only *queued* jobs can be timed out (`TTS_QUEUE_TIMEOUT`, checked both preemptively at enqueue and again when a job is dequeued).
- Response cache keyed by sha256(`voice`, `text`, `instruct`) in `TTS_CACHE_DIR` — wav is the cache unit; mp3 is generated from a cached wav on demand and separately cached.
- Optional idle-unload (`TTS_IDLE_UNLOAD` env var, default off) frees the ~6.7GB model after N idle seconds and lazily reloads on next request. The idle-watcher thread deliberately checks a `_worker_busy` flag before unloading — unloading mid-generation previously caused hung requests (see comment at `tts_daemon.py:382-385`).
- Every event (request/complete/cache_hit/error/model_reload/model_unload) is appended as JSONL to `TTS_TELEMETRY_LOG`, including a cheap system-load snapshot (`os.getloadavg` + `ps`) — useful for diagnosing why generation was slow.
- 300-char (`MAX_CHARS`) hard limit rejected before entering the queue; long-text auto-chunking across multiple `generate_audio()` calls + `ffmpeg concat` exists in the code (`chunk_text()`, the `multi` branch in `_generate`/`_run`) but is currently gated off — both `_run()` and `handle_request()` explicitly reject text over `MAX_CHARS` instead of using it.
- macOS Process QoS is best-effort bumped via `taskpolicy -s policy user-initiated` at startup — negative `nice` isn't available to a `launchd` user agent (see `_apply_process_qos()` docstring and README § Priority for why this barely matters: generation is GPU/Metal-bound, and QoS/nice only affects CPU scheduling).

**launchd service** (`launchd/com.liino.qwen-tts-daemon.plist`) runs the daemon at login with `RunAtLoad`+`KeepAlive`. The plist hardcodes absolute paths to this project's `.venv` — must be edited (and the service reinstalled with `launchctl load`/`unload`, not just edited in place) if the project moves.

## Conventions in this codebase

- Comments and docstrings are written in Thai; code identifiers and error/log messages are English. Match this when editing — don't switch a file's dominant comment language.
- `qwen_clone_tts.py` output contract: stdout gets exactly `OK <path>` on success; stderr gets `ERROR: ...` on failure plus a `TIMING ...` line either way. Scripts/agents parsing this output depend on that exact prefix.
- Mood presets (`MOOD_PRESETS` in `qwen_clone_tts.py`) are the preferred way to add new tone variants over ad-hoc `--instruct` strings — keep new moods short, English, and in the same "trait, trait, pacing" style as existing ones.
