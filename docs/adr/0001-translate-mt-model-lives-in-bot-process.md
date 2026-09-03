# MT model for `/translate` loads inside `discord_say_bot.py`, not `tts_daemon.py`

`/translate` needs a local LLM (`mlx-community/Qwen2.5-7B-Instruct-4bit`, ~4.5GB) to do JP→EN/TH
translation. `tts_daemon.py` already solves model lifecycle (queue, idle-unload, telemetry) for
the TTS model, so extending it to also serve translation requests was the more "consistent"
option on paper.

We chose to lazy-load the MT model as a module-level singleton inside `discord_say_bot.py`
instead. Reasons:

- The daemon's queue is a single FIFO worker built around one job shape (TTS generation);
  teaching it a second, structurally different job type (LLM chat completion) would touch
  the shared JSON-line protocol that Hermes and other consumers also depend on, for a feature
  that's Discord-only.
- The bot process is already the place ephemeral, request-scoped state lives (see ADR-0002);
  keeping the MT model there too means `/translate`'s two "new" pieces of state stay together.

Consequence: the bot process's steady-state RAM grows by ~4.5GB the first time anyone runs
`/translate` (no idle-unload — this trades memory for simplicity). If that becomes a real
problem, moving the LLM into a small sibling daemon (or into `tts_daemon.py` behind a second
request type) is the fallback; it wasn't done up front because no such pressure exists yet.
