# Qwen3-TTS for Mac - Run AI Text-to-Speech Locally on Apple Silicon

Run **Qwen3-TTS** text-to-speech AI locally on your MacBook with Apple Silicon (M1, M2, M3, M4). No cloud, no API keys, completely offline.

**Keywords:** Qwen TTS Mac, Qwen3 TTS Apple Silicon, MLX text to speech, local TTS Mac, voice cloning Mac, AI voice generator MacBook

> **Note for AI agents / automation:** this project has two entry points — `main.py` is an interactive human menu, `qwen_clone_tts.py` is a non-interactive CLI you can call directly with flags (no prompts). Use `qwen_clone_tts.py` for scripting. See [CLI Reference](#cli-reference-scripting--ai-agents) below. There is also an optional Discord bot (`discord_say_bot.py`) — see [Discord Bot](#discord-bot-discord_say_botpy) below.

---

## Features

| Feature | What it does | Entry point |
|---------|---------------|--------------|
| **Voice Cloning** | Clone any voice from a 5-10 second reference `.wav` clip | `main.py` (menu) / `qwen_clone_tts.py` |
| **Voice Design** | Create a new voice from a text description (e.g. "deep narrator") | `main.py` (menu) |
| **Custom Voice** | 9 built-in preset voices with emotion + speed control | `main.py` (menu) |
| **Scriptable CLI** | Generate audio from a single flag-based command, no prompts | `qwen_clone_tts.py --text ...` |
| **Stdin/file mode** | Read text from a file, auto-chunk long text, output one audio file | `qwen_clone_tts.py --stdin <in> <out>` |
| **WAV or MP3 output** | Generate MP3 directly via ffmpeg (`libmp3lame`) instead of WAV | `--mp3` flag |
| **Background daemon** | Load the model once, serve requests over a Unix socket — skips the ~3-10s model load on every call | `tts_daemon.py` |
| **FIFO job queue** | Daemon serializes concurrent requests; in-flight jobs are never cancelled | `tts_daemon.py` |
| **Response caching** | Identical `(voice, text, instruct)` requests return cached audio instantly | `tts_daemon.py` |
| **Idle model unload** | Daemon frees ~6.7GB RAM after N idle seconds, reloads automatically on next request | `TTS_IDLE_UNLOAD` env var |
| **JSONL telemetry** | Every request logged (timing, cache hits, system load) for debugging/analysis | `TTS_TELEMETRY_LOG` env var |
| **launchd service** | Run the daemon as a background macOS service that starts on login | `launchd/com.liino.qwen-tts-daemon.plist` |
| **100% Local** | Runs entirely on your Mac, no internet required after model download | — |
| **Optimized for M-Series** | Uses Apple's MLX framework for fast GPU inference | — |
| **Discord voice bot** | Prefix command `?say <text> [--mood ...]` makes the bot join your voice channel and speak with the Liino voice, via the daemon fast path | `discord_say_bot.py` |

---

## Why MLX Models?

MLX models are specifically optimized for Apple Silicon. Compared to running standard PyTorch models:

| Metric | Standard Model | MLX Model |
|--------|----------------|-----------|
| **RAM Usage** | 10+ GB | 2-3 GB |
| **CPU Temperature** | 80-90°C | 40-50°C |

*Tested on M4 MacBook Air (fanless) with 1.7B models*

MLX runs natively on the Apple Neural Engine and GPU, meaning better performance with less heat and battery drain.

---

## Quick Start (5 Minutes)

### 1. Clone and setup

```bash
git clone https://github.com/kapi2800/qwen3-tts-apple-silicon.git
cd qwen3-tts-apple-silicon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg
```

### 2. Download models

Pick the models you need from the table below. Click the link, then click "Download" on HuggingFace.

**Pro Models (1.7B) - Best Quality**

| Model | Use Case | Download |
|-------|----------|----------|
| CustomVoice | Preset voices + emotion control | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit) |
| VoiceDesign | Create voices from text description | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit) |
| Base | Voice cloning from audio | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit) |

**Lite Models (0.6B) - Faster, Less RAM**

| Model | Use Case | Download |
|-------|----------|----------|
| CustomVoice | Preset voices + emotion control | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit) |
| VoiceDesign | Create voices from text description | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-VoiceDesign-8bit) |
| Base | Voice cloning from audio | [Download](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit) |

Put downloaded folders in `models/`:
```
models/
├── Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit/
├── Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit/
└── Qwen3-TTS-12Hz-1.7B-Base-8bit/
```

### 3. Run (interactive)

```bash
source .venv/bin/activate
python main.py
```

---

## Usage (interactive menu)

```
========================================
 Qwen3-TTS Manager
========================================

  Pro Models (1.7B - Best Quality)
  ---------------------------------
  1. Custom Voice
  2. Voice Design
  3. Voice Cloning

  Lite Models (0.6B - Faster)
  ---------------------------
  4. Custom Voice
  5. Voice Design
  6. Voice Cloning

  q. Exit

Select: 
```

- **Custom Voice**: Pick from preset speakers, set emotion and speed
- **Voice Design**: Describe a voice (e.g., "calm British narrator")
- **Voice Cloning**: Provide a reference audio clip to clone

### Tips

- Drag `.txt` files directly into the terminal for long text
- Voice cloning works best with clean 5-10 second audio clips
- Speed options: Normal (1.0x), Fast (1.3x), Slow (0.8x)
- Type `q` or `exit` anytime to go back

---

## CLI Reference (scripting / AI agents)

`qwen_clone_tts.py` clones a voice from `voices/<name>.wav` (+ optional `voices/<name>.txt` reference transcript) and writes an audio file — no interactive prompts. It automatically uses the background daemon (see below) if one is running, and falls back to loading the model itself if not.

```bash
source .venv/bin/activate

# Basic: clone the default "Liino" voice
python qwen_clone_tts.py --text "Hello world" --out outputs/hello.wav

# Choose a voice, add a tone instruction, output MP3
python qwen_clone_tts.py \
  --text "สวัสดีครับ ยินดีต้อนรับ" \
  --voice Liino \
  --instruct "cheerful, bright, playful young female voice" \
  --mp3 \
  --out outputs/greeting.mp3
```

| Flag | Required | Description |
|------|----------|--------------|
| `--text "..."` | yes (unless `--stdin`) | Text to speak. **Max 300 characters** — longer text is rejected with an error. |
| `--voice NAME` | no (default `Liino`) | Voice name; must match `voices/NAME.wav` |
| `--out PATH` | no (default temp file) | Output audio path |
| `--mp3` | no | Convert output to `.mp3` via ffmpeg instead of `.wav` |
| `--instruct "..."` | no | Free-text tone/style description, e.g. `"calm British narrator"` |
| `--instruct-long` | no | Use the built-in long-form default instruct preset instead of `--instruct` |

**File / stdin mode** (reads text from a file, auto-chunks it, always uses the `Liino` voice):

```bash
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.mp3 --mp3
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav --instruct-long
```

Exit code `0` = success (`OK <path>` printed to stdout). Non-zero = failure (`ERROR: ...` printed to stderr).

---

## Daemon (`tts_daemon.py`)

Background service that loads the model **once** and serves generation requests over a Unix domain socket, so repeat calls skip the multi-second model-load cost. `qwen_clone_tts.py` automatically detects and uses the daemon if it's running — no code changes needed on the client side.

### Start it

```bash
.venv/bin/python tts_daemon.py
```

Or install as a launchd background service — see `launchd/com.liino.qwen-tts-daemon.plist` (edit paths for your install, then `launchctl load` it; you must reinstall the service yourself after editing the plist).

### Behavior

- **FIFO queue** — requests are served one at a time, in order. A job that is already generating is never cancelled mid-flight.
- **Queue timeout** — if a new request is estimated to wait longer than `TTS_QUEUE_TIMEOUT` seconds, the daemon rejects it immediately with `error: "queue timeout"` instead of making it wait.
- **Response caching** — identical `(voice, text, instruct)` requests return a cached file instantly (`cached: true` in the response), even after the model has been idle-unloaded.
- **300-char limit** — requests over `MAX_CHARS` (300) are rejected immediately, before entering the queue. Long-text chunking is currently disabled.
- **MP3 output** — request `"format": "mp3"` (or `--mp3` on the client). Audio is generated once as WAV, cached, then converted to MP3 with ffmpeg (`libmp3lame -q:a 4`) — it never regenerates from scratch for a format change.
- **Idle unload** — set `TTS_IDLE_UNLOAD` (seconds, default `0` = disabled). If no request arrives for longer than this, the daemon frees the model from RAM (~6.7GB) and reloads it automatically (~3s) on the next request. Cache hits still respond instantly even while the model is unloaded.
- **Telemetry** — every request/cache-hit/error is appended as one JSON line to `TTS_TELEMETRY_LOG`, including timing and a system load snapshot (`os.getloadavg` + `ps`).

### Config (environment variables)

| Var | Default | Description |
|-----|---------|--------------|
| `TTS_DAEMON_SOCK` | `/tmp/qwen_tts_daemon.sock` | Unix socket path |
| `TTS_CACHE_DIR` | `~/.cache/qwen_tts` | Audio cache directory |
| `TTS_QUEUE_TIMEOUT` | `60` | Seconds — reject a request instead of queueing it if it's estimated to wait longer than this |
| `TTS_TELEMETRY_LOG` | `~/Library/Logs/qwen_tts_daemon.log` | JSONL telemetry log path |
| `TTS_IDLE_UNLOAD` | `0` (disabled) | Seconds of inactivity before unloading the model from RAM |

### Protocol

Send one JSON object + `\n` over the Unix socket; receive one JSON response + `\n`.

```json
// request
{"text": "hello", "instruct": null, "out_path": "/tmp/out.wav", "voice": "Liino", "format": "wav"}

// response
{"ok": true, "out_path": "/tmp/out.wav", "gen_s": 3.2, "error": null, "cached": false, "queue_wait_s": 0.01, "format": "wav"}
```

The `qwen_clone_tts.py` client already implements this protocol — talk to the daemon directly only if you're building a new client.

### Priority (nice / Process QoS)

`launchd/com.liino.qwen-tts-daemon.plist` runs the daemon at normal `nice 0` — negative `nice` values (to prioritize the daemon over other processes, e.g. `-5`) require root, which a `launchd` **user agent** (`~/Library/LaunchAgents`) cannot grant. To actually get `-5`, move the plist to `/Library/LaunchDaemons` and run it as a system daemon via `sudo launchctl load ...`.

Instead, the daemon best-effort sets macOS Process QoS to `user-initiated` via `taskpolicy -s policy user-initiated` at startup (falls back to default QoS without failing if that call doesn't succeed).

Important caveat: Qwen3-TTS is GPU-bound (Metal) — macOS always prioritizes GPU access for the foreground app. `nice`/QoS only affect CPU scheduling. The only thing that reliably speeds up generation is reducing load from *other* GPU/CPU-heavy apps (Chrome tabs, Discord, etc.), not tuning the daemon's priority.

---

## Discord Bot (`discord_say_bot.py`)

Optional Discord bot that adds a prefix command `?say <text> [--mood <preset>]`: the bot joins the voice channel you're currently in, generates speech with the cloned "Liino" voice via the background daemon's fast path, and plays it back. It reuses `MAX_CHARS`, `MOOD_PRESETS`, and `_try_daemon()` from `qwen_clone_tts.py` directly — no duplicated logic.

This is a **text command**, not a Discord slash command, deliberately — to avoid clashing with other bots' slash command namespaces.

### Prerequisites (outside the code)

- The background daemon must be running (`tts_daemon.py`) — the bot **never** falls back to loading the model itself; if the daemon is down or fails, it replies with a clear error instead of hanging.
- In the [Discord Developer Portal](https://discord.com/developers/applications), enable the privileged **Message Content Intent** for this bot application — without it, the bot cannot read the text of `?say` commands and will appear to simply not respond.
- The bot needs `Connect` and `Speak` permissions in the target voice channel.

### Start it

```bash
# make sure the daemon is running first
.venv/bin/python tts_daemon.py &

# then start the bot (reads DISCORD_BOT_TOKEN from .env / process env)
.venv/bin/python discord_say_bot.py
```

### Behavior

- **`?say <text>`** — joins the voice channel of the message author and speaks `<text>` with the Liino voice.
- **`?say <text> --mood <preset>`** — same, but applies one of the mood presets from `qwen_clone_tts.py` (`excited`, `sleepy`, `whisper`, `storyteller`, etc.).
- Text over `MAX_CHARS` (300) is rejected immediately with a readable error — it is never queued.
- If you're not in a voice channel when you run `?say`, the bot replies with an error and does not join anything.
- **Playback queue per guild** — TTS generation always runs in a background thread (`asyncio.to_thread`) so it never blocks the bot's Discord heartbeat. Once audio is generated it's placed on a per-guild `asyncio.Queue`; a worker plays files one at a time via `discord.FFmpegPCMAudio`, waiting for each one to finish before starting the next — concurrent `?say` calls queue up instead of overlapping.
- **Idle-leave** — after the queue is empty and playback finishes, the bot waits `VC_IDLE_TIMEOUT_S` seconds (default 60) and then disconnects from the voice channel automatically. A new `?say` before that timer elapses cancels the countdown.
- **Daemon down = immediate error** — if the daemon socket isn't there or the daemon returns an error, the bot posts an error message right away and does **not** fall back to loading the model in-process (unlike `qwen_clone_tts.py`'s normal CLI behavior). This is intentional: loading the ~6.7GB model in the bot process would make the bot appear to hang for several seconds on every request.

### Config (environment variables)

| Var | Default | Description |
|-----|---------|--------------|
| `DISCORD_BOT_TOKEN` | *(required, secret)* | Discord bot token — put it in `.env`, never hardcode or commit it |
| `DISCORD_COMMAND_PREFIX` | `?` | Prefix for the bot's text commands |
| `VC_IDLE_TIMEOUT_S` | `60` | Seconds to wait in an idle voice channel (empty queue, nothing playing) before disconnecting |

---

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- ffmpeg (for MP3 output / long-text concatenation)
- RAM: ~3GB for Lite models, ~6GB for Pro models

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `mlx_audio not found` | Run `source .venv/bin/activate` first |
| `Model not found` | Check model folder names match exactly |
| Audio won't play | Check macOS sound output settings |
| `text is N chars — max is 300` | Split the text yourself; long-text auto-chunking is disabled |
| Daemon not picked up by client | Check `TTS_DAEMON_SOCK` matches on both daemon and client; confirm the daemon process is running |

---

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=kapi2800/qwen3-tts-apple-silicon&type=date&legend=top-left)](https://www.star-history.com/?repos=kapi2800%2Fqwen3-tts-apple-silicon&type=date&legend=top-left)


---

## Related Projects

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) - Original Qwen3-TTS by Alibaba
- [MLX Audio](https://github.com/Blaizzy/mlx-audio) - MLX framework for audio models
- [MLX Community](https://huggingface.co/mlx-community) - Pre-converted MLX models


---

**If this project helped you, please give it a ⭐ star!**
