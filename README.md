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
| **Stdin/file mode** | Read text from a file, switch mood mid-file via `[mood:xxx]` tags, output one audio file | `qwen_clone_tts.py --stdin <in> <out>` |
| **WAV or MP3 output** | Generate MP3 directly via ffmpeg (`libmp3lame`) instead of WAV | `--mp3` flag |
| **Background daemon** | Load the model once, serve requests over a Unix socket — skips the ~3-10s model load on every call | `tts_daemon.py` |
| **FIFO job queue** | Daemon serializes concurrent requests; in-flight jobs are never cancelled | `tts_daemon.py` |
| **Response caching** | Identical `(voice, text, instruct, lang)` requests return cached audio instantly | `tts_daemon.py` |
| **Idle model unload** | Daemon frees ~6.7GB RAM after N idle seconds, reloads automatically on next request | `TTS_IDLE_UNLOAD` env var |
| **JSONL telemetry** | Every request logged (timing, cache hits, system load) for debugging/analysis | `TTS_TELEMETRY_LOG` env var |
| **launchd service** | Run the daemon as a background macOS service that starts on login | `launchd/com.liino.qwen-tts-daemon.plist` |
| **100% Local** | Runs entirely on your Mac, no internet required after model download | — |
| **Optimized for M-Series** | Uses Apple's MLX framework for fast GPU inference | — |
| **Discord voice bot** | Slash command `/say text:<text>` or `/say file:<x.txt>` `[mood:<preset>] [voice:<name>]` — joins your voice channel and speaks with a cloned voice (default voice, or `voice:` to pick one) via the daemon; single-line `text` or a multi-line `.txt` upload, plus emoji auto-mood; `/transcribe` turns an audio upload into paste-ready text; `/voice-clone` create/list/edit/delete/test/set-default manages cloned voices from Discord (upload a clip → auto-transcribed reference) | `discord_say_bot.py` |

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
python fix_mlx_audio_assets.py  # one-time: patches missing mlx-audio whisper assets, see script docstring
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
| `--mood NAME` | no | Named tone preset (see mood list below) |
| `--lang CODE` | no (default `auto`) | Output language for the TTS model. `auto` lets the model infer it from the text. Valid: `auto, chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish`. **Thai is not a model language — Thai text uses `auto`.** |

**File / stdin mode** (reads text from a file, supports `[mood:xxx]` tags to switch mood mid-file, always uses the `Liino` voice):

```bash
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.mp3 --mp3
python qwen_clone_tts.py --stdin path/to/input.txt path/to/output.wav --mood excited
python qwen_clone_tts.py --stdin path/to/input.ja.txt out.wav --lang japanese

# input.txt may contain: [mood:excited]Hi there! [mood:sleepy]So tired now...
```

Untagged text is still capped at 300 chars (same limit as `--text`). Insert one or more `[mood:xxx]` tags (`xxx` must be a key from the mood list below) to switch tone mid-file — each tagged segment is generated separately and stitched together with `ffmpeg`, with no overall length limit. An unknown mood key in a tag fails the whole file with `ERROR: unknown mood(s) in --stdin tag: ...` before any audio is generated.

Exit code `0` = success (`OK <path>` printed to stdout). Non-zero = failure (`ERROR: ...` printed to stderr).

---

## Daemon (`tts_daemon.py`)

Background service that loads the model **once** and serves generation requests over a Unix domain socket, so repeat calls skip the multi-second model-load cost. `qwen_clone_tts.py` automatically detects and uses the daemon if it's running — no code changes needed on the client side.

### Start it

```bash
.venv/bin/python tts_daemon.py
```

Or install as a launchd background service — see `launchd/com.liino.qwen-tts-daemon.plist` (edit paths for your install, then `launchctl load` it; you must reinstall the service yourself after editing the plist).

### Restart it

`./restart_daemon.sh` wraps the `launchctl` incantations:

```bash
./restart_daemon.sh              # kickstart -k — pick up new tts_daemon.py code
./restart_daemon.sh --reinstall  # copy the repo plist into ~/Library/LaunchAgents/ then unload/load
                                 #   (needed whenever the plist changes — e.g. WorkingDirectory, env, Nice)
./restart_daemon.sh --manual     # unload the launchd agent, run tts_daemon.py in the foreground with live logs
./restart_daemon.sh --clear-cache# wipe TTS_CACHE_DIR before restarting
./restart_daemon.sh --verify     # after restart, fire one real request and fail unless it hits the daemon fast path
```

Flags combine (`./restart_daemon.sh --reinstall --verify`). The script honours `TTS_DAEMON_SOCK` / `TTS_CACHE_DIR` / `TTS_TELEMETRY_LOG` overrides and waits (up to 20s) for the socket to come back after the model reloads. `--manual` does not re-load the agent for you — it prints the `launchctl load` command to run when you're done.

### Behavior

- **FIFO queue** — requests are served one at a time, in order. A job that is already generating is never cancelled mid-flight.
- **Queue timeout** — if a new request is estimated to wait longer than `TTS_QUEUE_TIMEOUT` seconds, the daemon rejects it immediately with `error: "queue timeout"` instead of making it wait.
- **Response caching** — identical `(voice, text, instruct, lang)` requests return a cached file instantly (`cached: true` in the response), even after the model has been idle-unloaded. A request with no `lang` (or `lang: "auto"`) uses the same cache key it always did, so upgrading the daemon does not invalidate the existing cache.
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
{"text": "hello", "instruct": null, "out_path": "/tmp/out.wav", "voice": "Liino", "format": "wav", "lang": "auto"}

// response
{"ok": true, "out_path": "/tmp/out.wav", "gen_s": 3.2, "error": null, "cached": false, "queue_wait_s": 0.01, "format": "wav"}
```

`lang` is optional and defaults to `"auto"` (omitting it is identical to sending `"auto"`). Valid values are `auto` plus the model's language codes: `chinese, english, french, german, italian, japanese, korean, portuguese, russian, spanish`. An unknown code returns `ok: false`.

`out_path` **must be an absolute path**. The daemon's working directory is not the caller's (a `launchd`-run daemon has cwd `/`), so a relative path would be written in the wrong place — the daemon rejects it with `ok: false` / `error: "out_path must be absolute"`. The `qwen_clone_tts.py` client handles this automatically by `os.path.abspath()`-ing `out_path` before sending.

The `qwen_clone_tts.py` client already implements this protocol — talk to the daemon directly only if you're building a new client.

### Priority (nice / Process QoS)

`launchd/com.liino.qwen-tts-daemon.plist` runs the daemon at normal `nice 0` — negative `nice` values (to prioritize the daemon over other processes, e.g. `-5`) require root, which a `launchd` **user agent** (`~/Library/LaunchAgents`) cannot grant. To actually get `-5`, move the plist to `/Library/LaunchDaemons` and run it as a system daemon via `sudo launchctl load ...`.

Instead, the daemon best-effort sets macOS Process QoS to `user-initiated` via `taskpolicy -s policy user-initiated` at startup (falls back to default QoS without failing if that call doesn't succeed).

Important caveat: Qwen3-TTS is GPU-bound (Metal) — macOS always prioritizes GPU access for the foreground app. `nice`/QoS only affect CPU scheduling. The only thing that reliably speeds up generation is reducing load from *other* GPU/CPU-heavy apps (Chrome tabs, Discord, etc.), not tuning the daemon's priority.

---

## Discord Bot (`discord_say_bot.py`)

Optional Discord bot that adds an application slash command `/say`: pass either `text:<text>` (a single line) or `file:<x.txt>` (a `.txt` attachment for multi-line input), plus an optional `mood:<preset>` and `voice:<name>`. The bot joins the voice channel you're currently in, generates speech with a cloned voice via the background daemon's fast path, and plays it back. It reuses `MAX_CHARS`, `MOOD_PRESETS`, `resolve_instruct()`, and `_try_daemon()` from `qwen_clone_tts.py` directly — no duplicated logic. A second command, `/transcribe`, converts an uploaded audio file into paste-ready `/say` text (see below).

The command tree is synced on `on_ready`. If `DISCORD_GUILD_ID` is set, `/say` is registered to just that guild and appears instantly; otherwise it's registered globally and can take up to ~1 hour to show up the first time.

### Prerequisites (outside the code)

- The background daemon must be running (`tts_daemon.py`) — the bot **never** falls back to loading the model itself; if the daemon is down or fails, it replies with a clear error instead of hanging.
- The bot's invite URL must include the `applications.commands` scope (in addition to `bot`), otherwise the `/say` command can't be registered. No privileged **Message Content Intent** is needed — slash commands don't read message text.
- The bot needs `Connect` and `Speak` permissions in the target voice channel, plus `Send Messages` in the text channel where `/say` is used (the queue confirmation is posted there).
- `DISCORD_BOT_TOKEN` must be exported as a real process environment variable — this project does **not** auto-load a `.env` file (config is env-var-only, no config file, same as `tts_daemon.py`). The `.env` at the repo root is unrelated tooling config (Notion token for the kanban skill), not read by any TTS script.

### Start it

```bash
# make sure the daemon is running first
.venv/bin/python tts_daemon.py &

# then start the bot (DISCORD_BOT_TOKEN must already be exported in this shell)
export DISCORD_BOT_TOKEN=...
export DISCORD_GUILD_ID=...   # optional — register /say to just this guild (instant)
.venv/bin/python discord_say_bot.py
```

### Behavior

- **`/say text:<text>`** — joins the voice channel of the command user and speaks `<text>` with the current default voice (or `voice:<name>` if given). `text` is meant for a single line (Discord desktop can't type a newline in a slash field).
- **`voice:<name>`** — override the voice for this call only (autocomplete lists names from `voices/`, filtered as you type — dynamic rather than a static dropdown, so it still works past Discord's 25-choice limit). An unknown/unsanitizable name is rejected with an ephemeral error before anything is queued. Leave it unset to use the default voice set via `/voice-clone set-default` (falls back to `Liino` if none was ever set). If the chosen voice has a stored `instruct.txt`, it's used as the instruct fallback when no `mood`/explicit instruct is given, and it's also *composed* onto `mood:<preset>` (voice text first, mood trait appended) so a voice's gender/timbre stays fixed while the mood trait still applies — before the built-in default (see `resolve_instruct()`).
- **`/say file:<x.txt>`** — upload a UTF-8 `.txt` attachment (≤ 100 KB) for multi-line input: one line per sentence, real newlines in the file. Same pipeline as `text` (emoji auto-mood, per-line limit, etc.).
- **You must supply exactly one of `text:` or `file:`** — neither or both is rejected with an ephemeral error before anything is queued. A `file:` that isn't `.txt`, is over 100 KB, or isn't valid UTF-8 is rejected the same way.
- **`mood:<preset>`** — applies one of the mood presets from `qwen_clone_tts.py` (`excited`, `sleepy`, `whisper`, `storyteller`, `pouty`, `shy`, `proud`, `worried`, etc.), picked from the `mood` choice dropdown. Works with both `text:` and `file:`.
- **`language:<code>`** — pin the TTS output language (`japanese`, `english`, `chinese`, …) so text isn't mispronounced in the wrong language. Leave it unset for `auto` (the model infers language from the text; Thai always uses `auto`). Applies to every line of a `text:` or `file:` request.
- **Multi-line handling** — each line is spoken one per sentence, queued in order (each line generated separately, then played back-to-back with a short `SAY_SENTENCE_GAP_S` pause between them). Blank / whitespace-only lines are skipped. There is no cap on the number of lines (longer messages just take longer to generate through the daemon's FIFO queue).
- **Ephemeral replies** — usage hints and every error (over-limit line, no voice channel, daemon down, etc.) are sent as an ephemeral reply visible only to the command user. On success the queue confirmation (`🔊 เข้าคิวแล้ว N บรรทัด`) is posted to the channel.
- **Emoji auto-mood** — the first recognised emoji on a line sets that line's mood and is removed from the spoken text (e.g. `😄สวัสดี` → says "สวัสดี" with the `excited` mood). An explicit `mood:` choice always overrides emoji. Unrecognised emoji are left in the text and don't change the mood. Emoji → mood map:

  | mood | emoji |
  |---|---|
  | `excited` | 😄 😁 😃 🎉 ⚡ |
  | `giggle` | 😆 🤣 😂 😹 |
  | `surprised` | 😮 😲 😯 😱 |
  | `sad` | 😢 😭 😔 💔 |
  | `angry` | 😠 😡 😤 |
  | `sleepy` | 😴 😪 🥱 |
  | `whisper` | 🤫 🤐 |
  | `gentle` | 🥺 🤗 💗 |
  | `bored` | 😑 😐 🙄 |
  | `storyteller` | 📖 📚 🧚 |
  | `pouty` | 😒 😾 🫤 |
  | `shy` | 😳 🫣 |
  | `proud` | 😌 😏 |
  | `worried` | 😟 😧 😦 |
  | `scared` | 😨 😰 🙀 |
  | `confused` | 😕 🤔 😵 |

- The `MAX_CHARS` (300) limit applies **per line** (measured after emoji removal and trimming), matching the daemon's own per-request limit. If any single line is over 300 chars, the whole message is rejected immediately with a readable error naming the offending line number, and nothing is queued. The combined length of all lines is not limited.
- **Atomic batch** — if any line fails to generate (daemon down mid-batch), no line is played and the temp files are cleaned up.
- If you're not in a voice channel when you run `/say`, the bot replies with an ephemeral error and does not join anything.
- **Playback queue per guild** — TTS generation always runs in a background thread (`asyncio.to_thread`) so it never blocks the bot's Discord heartbeat. Once audio is generated it's placed on a per-guild `asyncio.Queue`; a worker plays files one at a time via `discord.FFmpegPCMAudio`, waiting for each one to finish before starting the next — concurrent `/say` calls queue up instead of overlapping.
- **Idle-leave** — after the queue is empty and playback finishes, the bot waits `VC_IDLE_TIMEOUT_S` seconds (default 60) and then disconnects from the voice channel automatically. A new `/say` before that timer elapses cancels the countdown.
- **Daemon down = immediate error** — if the daemon socket isn't there or the daemon returns an error, the bot posts an error message right away and does **not** fall back to loading the model in-process (unlike `qwen_clone_tts.py`'s normal CLI behavior). This is intentional: loading the ~6.7GB model in the bot process would make the bot appear to hang for several seconds on every request.

### Config (environment variables)

| Var | Default | Description |
|-----|---------|--------------|
| `DISCORD_BOT_TOKEN` | *(required, secret)* | Discord bot token — export as a process env var, never hardcode or commit it (not auto-loaded from `.env`) |
| `DISCORD_GUILD_ID` | *(unset)* | If set, register `/say` to just this guild — it appears instantly. Unset = global registration (can take up to ~1 hour to appear the first time). |
| `VC_IDLE_TIMEOUT_S` | `60` | Seconds to wait in an idle voice channel (empty queue, nothing playing) before disconnecting |
| `SAY_SENTENCE_GAP_S` | `0.5` | Seconds of silence inserted after each sentence before the next queued line plays. `0` disables it. |
| `TRANSCRIBE_WHISPER_MODEL` | `mlx-community/whisper-large-v3-turbo` | Whisper model repo used by `/transcribe` for speech-to-text. The first `/transcribe` after startup downloads ~1.6 GB to the Hugging Face cache. Set to `mlx-community/whisper-large-v3` for higher accuracy at the cost of speed and memory. |

### `/transcribe` — audio file → paste-ready `/say` text

Upload an `.mp3` or `.wav` and the bot transcribes it locally with Whisper
(`mlx-whisper`, no cloud), tags each line with a mood emoji, and replies with a
`.txt` attachment you can drop straight into `/say file:`.

- **`/transcribe file:<audio> [mood:<preset>] [language:<th|ja|en>]`** — `file`
  must be `.mp3` or `.wav`, ≤ 20 MB and ≤ 10 minutes; anything else is rejected
  with an ephemeral error and nothing is posted.
- **`language:`** — leave it unset (default) and Whisper auto-detects the spoken
  language from the start of the clip and uses that one language for the whole
  file (prevents mixed-language output, e.g. a Japanese clip partly transcribed
  as Thai). Pick `th` / `ja` / `en` to force a language.
- Each Whisper segment becomes one line. A per-line keyword heuristic (Thai +
  English + Japanese) picks a mood and prefixes the matching emoji (`😄`, `😢`,
  `🤫`, …) — the same emoji `/say` reads back as auto-mood. Lines with no match
  get no prefix.
- **`mood:<preset>`** overrides the mood for **every** line. `default` and
  `long` have no emoji, so choosing them emits lines with no prefix.
- The reply is always a `.txt` attachment. When the text is ≤ 1800 characters it
  is also shown inline in a code block; longer transcripts are attachment-only.
- This command never touches the TTS daemon — it works even when the daemon is
  down.
- First run downloads the Whisper model (~1.6 GB, see
  `TRANSCRIBE_WHISPER_MODEL`). It loads once and stays in the bot process.

### `/voice-clone` — manage cloned voices from Discord

A command group for creating and managing the voices in `voices/` without
touching the filesystem by hand. All subcommands are guild-only and replies are
ephemeral (only the caller sees them). The file operations live in
`voice_store.py` (a pure module, no `discord` import) so they're unit-tested
independently of the bot.

- **`/voice-clone create name:<name> file:<audio> [instruction:<text>] [overwrite:<bool>]`**
  — upload a reference clip (`.mp3` / `.wav` / `.m4a` / `.ogg`, ≤ 25 MB, ≥ 3 s).
  The clip is converted to mono 24 kHz and trimmed to the first 12 s, saved as
  `voices/<name>.wav`, then transcribed with Whisper into `voices/<name>.txt`
  (improves cloning quality). An optional `instruction` — a short English tone
  description in the same style as the `MOOD_PRESETS` — is stored in
  `voices/<name>.instruct.txt`. Names are limited to `a-z 0-9 _` (1–32 chars).
  `Liino` is protected: overwriting it needs `overwrite:true`.
- **`/voice-clone list`** — lists every voice with its transcript status,
  stored instruction, and marks `(default)` next to the current default voice.
- **`/voice-clone set-default name:<name>`** — sets the voice `/say` uses when
  no `voice:` is given. Stored in `voices/.default` (one line, plain text);
  rejects names that don't exist yet. Falls back to `Liino` if `.default` is
  missing or points at a voice that was since deleted.
- **`/voice-clone edit name:<name> [instruction:<text>] [rename:<new>]`** —
  updates the stored instruction (send an empty `instruction` to clear it)
  and/or renames the voice (moves `.wav` / `.txt` / `.instruct.txt` together).
  Renaming the current default voice is rejected — `set-default` to a
  different voice first.
- **`/voice-clone delete name:<name> confirm:<true>`** — removes all three
  files. `confirm:true` is required; `Liino` and the current default voice
  cannot be deleted (`set-default` elsewhere first for the latter).
- **`/voice-clone test name:<name> [text:<text>] [mood:<preset>]`** — generates
  a short sample with that voice via the daemon fast path and posts the `.wav`.
  Instruction priority: `mood` preset > the voice's stored instruction >
  default.

`/say voice:<name>` (see above) plays any cloned voice, not just the default —
`/voice-clone set-default` only controls what `/say` uses when `voice:` is
omitted.

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
| `text is N chars — max is 300` | Split with `[mood:xxx]` tags for `--stdin`, or split the text yourself for `--text` |
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
