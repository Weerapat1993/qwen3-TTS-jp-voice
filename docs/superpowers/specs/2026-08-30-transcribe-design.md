# TTS-1005 — `/transcribe` Design

Date: 2026-08-30
Ticket: `obsidian/kanban/tasks/TTS-1005.md`
Status: design approved, pending implementation plan

## 1. Overview

Add an application slash command `/transcribe file:<audio>` to `discord_say_bot.py`.

Pipeline: audio attachment → local Whisper speech-to-text (mlx-whisper, no cloud) →
per-segment lines → Thai/English keyword mood heuristic → canonical emoji prefix per
line → reply with a `.txt` attachment that pastes directly into `/say file:`, plus an
inline preview when the text is short.

Output is **text only**. The command does not join a voice channel, does not play
audio, and does not touch `tts_daemon.py`, `qwen_clone_tts.py`, or `GuildPlayback`.

Out of scope: real-time VC playback of the transcript, speaker diarization, non-audio
attachments, tone analysis from the audio waveform (mood is derived from the
transcribed text only).

## 2. User-confirmed decisions

From `TTS-1005.md` "Decisions" + brainstorming on 2026-08-30:

1. **STT engine**: local Whisper via `mlx-whisper` (Apple Silicon, matches the
   project's no-cloud theme).
2. **Whisper model**: default `mlx-community/whisper-large-v3-turbo`
   (~1.6 GB, ~800M params — best Thai accuracy/speed tradeoff on Apple Silicon),
   overridable with the `TRANSCRIBE_WHISPER_MODEL` env var. Model is lazy-loaded once
   on the first `/transcribe` call and kept in the bot process for the process
   lifetime.
3. **Mood detection**: curated Thai + English keyword/substring table over the
   transcribed text. The `mood:` slash option, when supplied, overrides the mood for
   **every** line.
4. **Command name**: `/transcribe`.
5. **Limits**: attachment ≤ 20 MB **and** audio duration ≤ 10 minutes (600 s).
   Over either limit → ephemeral reject, nothing posted.
6. **Output**: always attach a `.txt` file (paste-ready for `/say file:`). Also show
   the text inline in-channel when the composed body is ≤ 1800 characters; otherwise
   the reply is the attachment plus a short note.
7. **Accepted formats**: `.mp3` and `.wav`. Any other extension → ephemeral reject.

## 3. Module layout

Follows the existing split (`say_moods.py` is pure logic, unit-tested, no `discord`
or `qwen_clone_tts` import; `discord_say_bot.py` is the Discord glue).

### 3.1 `stt_transcribe.py` (new)

Whisper wrapper. No `discord` import.

- `WHISPER_MODEL` — module constant read from
  `os.environ.get("TRANSCRIBE_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")`.
- `transcribe(audio_path: str) -> list[str]`
  - Calls `mlx_whisper.transcribe(audio_path, path_or_hf_repo=WHISPER_MODEL,
    language="th")`.
  - Returns each result segment's `text`, stripped, with empty segments dropped.
    Order preserved. Segments are the pragmatic "one line = one utterance" unit —
    Thai text has no reliable sentence delimiters, so no further splitting is done.
  - mlx-whisper loads/caches model weights internally (HF cache); first call for a
    given model triggers the ~1.6 GB download. No explicit global cache needed in
    this module beyond what mlx-whisper already does, but a thin module-level guard
    may be added if profiling shows repeated load cost.
- `probe_duration(audio_path: str) -> float` — runs
  `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 <path>`
  and returns seconds as a float. Raises on ffprobe failure (caller converts to an
  ephemeral error). `ffprobe` ships with the `ffmpeg` install already required by
  the project.

### 3.2 `transcribe_mood.py` (new)

Pure logic. No `discord`, no `qwen_clone_tts`, no `mlx` import. Unit-tested in
isolation like `say_moods.py`.

- `MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]]` — ordered list; each entry maps
  a tuple of lowercase substrings to a mood name. The mood name is always one that
  `say_moods.EMOJI_MOOD` recognizes, so a canonical emoji always exists.
  Initial table (refined during implementation, Thai + English):
  - giggle: `555`, `ฮ่า`, `ขำ`, `lol`, `haha`
  - sad: `เศร้า`, `เสียใจ`, `ร้องไห้`, `ผิดหวัง`, `sad`, `sorry`
  - angry: `โกรธ`, `โมโห`, `หงุดหงิด`, `angry`
  - surprised: `ตกใจ`, `ว้าว`, `ไม่น่าเชื่อ`, `wow`, `omg`
  - sleepy: `ง่วง`, `เหนื่อย`, `หลับ`, `tired`, `sleepy`
  - whisper: `กระซิบ`, `เงียบ ๆ`, `แอบบอก`, `whisper`, `secret`
  - gentle: `ไม่เป็นไรนะ`, `ใจเย็น`, `กอด`, `there there`
  - excited: `เย้`, `สุดยอด`, `ตื่นเต้น`, `ไปกันเลย`, `yay`, `let's go`
  - bored: `เบื่อ`, `น่าเบื่อ`, `เฉย ๆ`, `bored`, `meh`
  - storyteller: `กาลครั้งหนึ่ง`, `นานมาแล้ว`, `once upon a time`
- `detect_mood(text: str) -> str | None`
  - Lowercases `text`, returns the mood of the first `MOOD_KEYWORDS` entry with any
    substring present. No match → `None`.
  - Deterministic, order-sensitive; earlier entries win.

### 3.3 `say_moods.py` (edit)

Add the reverse map used to prefix lines:

```python
# mood name -> one canonical emoji that extract_mood() maps back to the same mood.
# Picked as the first emoji of each EMOJI_MOOD group. Moods without an emoji
# (default, long) are intentionally absent.
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

No change to `parse_lines`, `first_line_over_limit`, `extract_mood`.

### 3.4 `discord_say_bot.py` (edit)

New command; imports `stt_transcribe` and `transcribe_mood` (module top, alongside
the existing `say_moods` import). Reuses `MOOD_PRESETS` for the `mood:` choice list.

```
@tree.command(name="transcribe", description="ถอดเสียงไฟล์เสียงเป็นข้อความ + emoji mood พร้อมใช้กับ /say")
@app_commands.guild_only()
@app_commands.describe(
    file="ไฟล์เสียง .mp3 หรือ .wav (≤ 20 MB, ≤ 10 นาที)",
    mood="บังคับ mood ทุกบรรทัด (ไม่เลือก = auto จากข้อความ)")
@app_commands.choices(mood=[Choice(name=m, value=m) for m in sorted(MOOD_PRESETS)])
async def transcribe(interaction, file: discord.Attachment, mood: str | None = None): ...
```

## 4. Command flow

1. **Pre-defer validation** (ephemeral `interaction.response.send_message`, nothing
   posted to channel):
   - `file.filename` lowercased must end `.mp3` or `.wav`, else reject.
   - `file.size > 20 * 1024 * 1024` → reject ("ไฟล์ใหญ่เกิน 20 MB").
   - `mood` (if given) is already constrained to `MOOD_PRESETS` by the choice list;
     no extra check needed, but `resolve` is not called — `mood` is used only to
     look up `MOOD_EMOJI` (see step 6). A `mood` value with no `MOOD_EMOJI` entry
     (`default`, `long`) means "no emoji prefix, but still an explicit override" —
     i.e. lines get no emoji. Documented in the behavior section.
2. `await interaction.response.defer(ephemeral=True, thinking=True)` — STT is slow.
3. Download attachment to a temp file
   (`tempfile.gettempdir()/qwen_transcribe_<pid>_<ms>.<ext>`). On
   `discord.DiscordException` → ephemeral `followup` error, cleanup.
4. `duration = await asyncio.to_thread(stt_transcribe.probe_duration, path)`.
   - ffprobe failure → ephemeral "อ่านไฟล์เสียงไม่สำเร็จ", cleanup.
   - `duration > 600` → ephemeral "เสียงยาวเกิน 10 นาที", cleanup.
5. `lines = await asyncio.to_thread(stt_transcribe.transcribe, path)`.
   - Exception (model load / decode) → ephemeral error naming the cause, cleanup,
     bot stays up.
   - `not lines` → ephemeral "ถอดเสียงไม่พบข้อความ", cleanup.
6. Compose output. For each line:
   - `m = mood or transcribe_mood.detect_mood(line)`
   - `prefix = f"{MOOD_EMOJI[m]} " if m in MOOD_EMOJI else ""`
   - `composed_line = f"{prefix}{line}"`
   - `body = "\n".join(composed_lines)`
7. Reply (success → normal channel visibility):
   - Always: `discord.File` from an in-memory `io.BytesIO(body.encode("utf-8"))`
     named `transcribe_<interaction.id>.txt`.
   - If `len(body) <= 1800`: `interaction.channel.send(content=f"```\n{body}\n```",
     file=<txt>)`.
   - Else: `interaction.channel.send(content="📝 ถอดเสียงเสร็จแล้ว (ข้อความยาว — ดูไฟล์แนบ)",
     file=<txt>)`.
   - Then `interaction.followup.send("✅ เสร็จแล้ว", ephemeral=True)` to clear the
     spinner.
8. `finally`: remove the temp audio file (`os.remove`, ignore `OSError`).
9. `print(..., file=sys.stderr)` one telemetry line:
   `transcribe guild=<id> bytes=<n> dur_s=<f> lines=<n> model=<name> explicit_mood=<m>`.

## 5. Error handling summary

| Case | Response | Channel post? |
|---|---|---|
| Wrong extension | ephemeral | no |
| > 20 MB | ephemeral | no |
| Download failure | ephemeral followup | no |
| ffprobe failure | ephemeral followup | no |
| > 10 min | ephemeral followup | no |
| Whisper load / decode error | ephemeral followup, bot stays up | no |
| Empty transcript | ephemeral followup | no |
| Success | `.txt` + optional inline text | yes |

TTS daemon state is never read → daemon down has no effect on this command (AC).

## 6. Config and documentation

- `requirements.txt`: add `mlx-whisper==0.4.3` (current release; pin like the rest of
  the file).
- New env var `TRANSCRIBE_WHISPER_MODEL`:
  - Add a row to the README §Discord Bot "Config (environment variables)" table:
    default `mlx-community/whisper-large-v3-turbo`, "Whisper model repo for
    `/transcribe` STT. First run downloads ~1.6 GB to the Hugging Face cache."
  - Add a `/transcribe` subsection under §Discord Bot describing behavior, limits,
    accepted formats, output shape, and the round-trip into `/say file:`.
- No new Discord intent (AC). `ffmpeg`/`ffprobe` already listed as prerequisites.
- Per `kanban-flow.md` post-implementation step 2, the README env table update ships
  in the same change as the code.

## 7. Validation

No automated test suite for the Discord/STT paths; pure logic gets pytest.

**Automated (`pytest`):**
- `test_say_moods.py`: for every `(mood, emoji)` in `MOOD_EMOJI`,
  `extract_mood(f"{emoji} ข้อความ") == ("ข้อความ", mood)` (round-trip guarantee).
- `test_transcribe_mood.py` (new): representative Thai + English lines →
  expected mood; no-keyword line → `None`; ordering (a line hitting two tables
  returns the earlier one).

**Manual / live:**
- Upload a real Thai `.mp3` and a real `.wav` in Discord → transcript text is
  correct, emoji prefixes are plausible per line.
- Copy the `.txt` into `/say file:` → Liino speaks each line with the mood implied
  by its emoji (end-to-end round trip).
- `mood:excited` supplied → every line prefixed 😄 regardless of content.
- Reject cases: `.pdf` upload, a > 20 MB file, a > 10 min audio, a silent/empty
  audio clip → each returns an ephemeral error and posts nothing to the channel.
- Long transcript (many segments, body > 1800 chars) → reply is attachment + note,
  no inline block, no crash.
- Bot process survives a forced Whisper load failure (e.g. bogus
  `TRANSCRIBE_WHISPER_MODEL`) → ephemeral error, other commands still work.

## 8. Risks / open considerations

- **Thai accuracy of `large-v3-turbo`** — acceptable per general benchmarks; if live
  testing shows poor Thai output, switch the default to `mlx-community/whisper-large-v3`
  (slower, larger) via the same env var — no code change.
- **Model memory** — Whisper turbo (~1.6 GB) loads in the bot process, separate from
  the daemon's ~6.7 GB TTS model (different process). Combined host RAM should be
  checked on the target machine; documented as a prerequisite note.
- **First-call latency** — the first `/transcribe` after bot start pays the model
  download + load. The `defer(thinking=True)` spinner covers it; no pre-warm in this
  ticket.
- **Segment granularity** — Whisper segments, not true sentences. Occasionally a
  segment is a long run-on or a fragment. Accepted for v1; `/say` already handles
  arbitrary per-line length up to `MAX_CHARS` and rejects over-limit lines with a
  clear message.
- **`mood: default` / `mood: long`** — valid choices with no `MOOD_EMOJI` entry;
  treated as "explicit override, no emoji prefix". Slightly surprising but
  internally consistent; documented.
