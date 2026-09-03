# `/translate`'s ephemeral clone is a temp-named file inside `voices/`, not a scratch dir

`/translate` clones a voice from the uploaded audio for one request only (see CONTEXT.md,
"Ephemeral Voice") — it's never meant to appear in `/voice-clone list`. The obvious-looking
choice is to keep it fully out of `voices/` (e.g. write it to a tempdir and pass its path
straight into `mlx_audio.tts.generate.generate_audio()`).

We didn't do that. Both `tts_daemon.py`'s JSON protocol and `qwen_clone_tts.py`'s `_try_daemon`/
`_run_multi` resolve a voice by *name*, always joining it against `VOICES_DIR` — there is no
"give me a ref_audio path directly" request shape. Adding one means changing the wire protocol
that Hermes (a separate project) also speaks against, for a Discord-only feature.

Instead, `/translate` writes the trimmed reference clip to `voices/_translate_<interaction_id>.wav`
— a name shaped so it can never collide with a real, sanitize_name()-validated Voice (those are
`^[a-z0-9_]{1,32}$`, no leading underscore reachable through `/voice-clone create`) — calls the
existing daemon path exactly like any named Voice would, and deletes the file in a `finally`
block once generation completes or fails.

Consequence: a crash between write and cleanup leaves a stray `_translate_*.wav` sitting in
`voices/` (harmless — it's not a valid Voice name so nothing will ever address it, and it's
obvious debris to spot and delete by hand). If the daemon protocol ever grows inline
`ref_audio` support for other reasons, `/translate` should switch to that and stop touching
`voices/` at all.
