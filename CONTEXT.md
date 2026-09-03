# Qwen3-TTS Apple Silicon Runner

Local voice pipeline for Apple Silicon: clone a voice from a short reference clip, then drive it with text (typed, transcribed, or translated) to produce speech — all on-device via MLX, no cloud calls.

## Language

**Voice**:
A named, persistent identity in `voices/<name>.wav` (+ optional `.txt` transcript, `.instruct.txt` default tone) that `/say` and other commands can address by name. Created via `/voice-clone create`.
_Avoid_: Speaker, character (character is a looser Hermes-side concept; a Voice is the on-disk artifact)

**Ephemeral Voice**:
A Voice created and consumed within a single command invocation, never surfaced to `/voice-clone list` as a real option — it still lives at `voices/<temp-name>.wav` for the duration of the request (the daemon protocol only resolves voices by name in `VOICES_DIR`), but is deleted in a `finally` block once generation finishes. Used by `/translate`, which has no reason to keep the uploaded speaker's clone around.
_Avoid_: Temporary voice, throwaway clone

**Reference Clip**:
The short (≤`REF_TRIM_SECONDS`, currently 12s) mono 24kHz audio snippet a Voice is cloned from. `voice_store.prepare_ref_audio()` is the one function that produces this from any uploaded audio, trimming and reformatting it — every command that clones a voice from user audio (`/voice-clone create`, `/translate`) goes through it rather than re-implementing the ffmpeg trim.
_Avoid_: Sample, reference audio (reference audio is fine informally, but "Reference Clip" is the canonical term when writing docs/comments)

**Mood**:
A named emotional preset (key into `MOOD_PRESETS`) that resolves to an `instruct` string describing vocal delivery to the TTS model. Detected automatically from text via `detect_mood()`, or chosen explicitly by the caller — explicit always wins.
_Avoid_: Emotion, tone, vibe

**Instruct**:
The free-text vocal-delivery description actually sent to the TTS model (`resolve_instruct()`'s output) — composed from Mood, a Voice's own default instruction, or an explicit override, in that priority order.
_Avoid_: Prompt, style string

**Source Language / Target Language**:
Source Language is the language spoken in an uploaded audio file (what STT is told to expect, or `auto` to detect). Target Language is the language TTS output should be spoken in (a `LANG_CODES` entry, or `auto`). These are never the same axis — a `/translate` request has exactly one Source Language and one-or-two Target Languages.
_Avoid_: Input language / output language

**Transcript**:
The plain-text result of running STT (`stt_transcribe.transcribe()`) on an audio file, joined into one document. Distinct from a Translation, which is a Transcript rendered into a different Target Language by the MT step.
_Avoid_: Text, script

**Translation**:
A Transcript rewritten into a Target Language by the local MT model, as one whole-document call (not per-segment) so the model has full-sentence context. One Translation exists per requested Target Language.
_Avoid_: Translated text

**Chunk**:
A ≤`MAX_CHARS`-sized slice of text that a single TTS generation call can accept. `chunk_text()` splits any longer document (like a Translation) at sentence boundaries; `_run_multi()` generates one audio part per Chunk and concatenates them with ffmpeg into the final clip callers see.
_Avoid_: Segment (Segment is reserved for STT's per-utterance output, a different unit)

## Note on this file

`CONTEXT.md` was created during the `/translate` feature's domain-modeling session — most of the vocabulary above predates that feature but had never been written down. See `docs/adr/` for the two decisions made while designing `/translate` that a future reader would otherwise find surprising.
