# TTS-1012 — Inline Mood Tag (`[mood:xxx]`) Design

Date: 2026-08-30
Ticket: `obsidian/kanban/tasks/TTS-1012.md`
Status: design approved, pending implementation plan

## 1. Overview

Let a single `--stdin` batch text file switch mood mid-file via an inline tag
`[mood:xxx]`, so one Hermes-style text file can carry multiple emotional tones
instead of one `--mood`/`--instruct` for the whole file.

Pipeline: raw text → regex-split into `(mood_key | None, text_segment)` pairs →
validate every mood key against `MOOD_PRESETS` up front (fail whole run before any
generation) → each segment run through the existing `chunk_text()` → each resulting
chunk generated with `resolve_instruct(segment_mood, None, voice_default)` → concat
with ffmpeg.

**Correction from initial draft (2026-08-30, post-brainstorming code check):** the
concat mechanism this design needs is *not* an existing active path. `_run()` has a
`multi`-branch (generate-per-chunk + ffmpeg concat) but `multi = False` is hardcoded
(`qwen_clone_tts.py:235`), and text over `MAX_CHARS` is hard-rejected before that
branch is ever reached (`qwen_clone_tts.py:231-234`) — this is documented as
intentional in `CLAUDE.md` ("currently gated off"). Any file with 2+ mood tags
always needs 2+ generate calls stitched together, regardless of per-segment length,
so **this ticket reactivates that path**, scoped narrowly (§5) — user confirmed this
expanded scope explicitly rather than leaving it as a silent assumption.

Out of scope: emoji→mood auto-mapping, `discord_say_bot.py` mood dropdown, the plain
`--text`/`--instruct`/`--mood` CLI branch (stays single-instruct), any change to
`tts_daemon.py`'s request/response protocol.

## 2. User-confirmed decisions

From `TTS-1012.md` "Open Questions" + brainstorming on 2026-08-30:

1. **Tag syntax**: `[mood:xxx]`, unchanged from the original proposal. User confirmed
   Hermes sends plain natural-language text with no `[...]` brackets today, so
   collision risk is accepted as none — no need for a more exotic delimiter.
2. **Unknown mood key** (e.g. `[mood:exicted]`, not in `MOOD_PRESETS`): **fail the
   whole file**, loudly, before any generation starts. No partial output, no silent
   fallback to default — a typo should be obvious immediately, not buried in one
   oddly-toned segment.
3. **Parser style**: regex split (flexible) over line-anchored tags. A tag may sit
   anywhere in the text (start of a paragraph, mid-line); it does not have to be its
   own line. Chosen for flexibility — `chunk_text()` already owns sentence/whitespace
   boundary logic downstream, so the tag parser doesn't need to impose its own line
   discipline.

## 3. Parsing

New function in `qwen_clone_tts.py` (co-located with `chunk_text()`, same file per
CLAUDE.md single-source-of-truth convention):

```python
_MOOD_TAG_RE = re.compile(r"\[mood:(\w+)\]")

def split_mood_segments(text: str) -> list[tuple[str | None, str]]:
    """แบ่งข้อความตาม [mood:xxx] tag คืน list ของ (mood_key, text_segment)
    mood_key เป็น None สำหรับเนื้อความก่อน tag แรก (ถ้ามี)"""
```

- `re.split(_MOOD_TAG_RE, text)` on the capturing group interleaves plain text and
  matched mood keys: `[pre_text, key1, text1, key2, text2, ...]`.
- Walk that list pairwise to build `(mood_key, segment)` tuples. The leading element
  (before any tag) gets `mood_key=None`.
- Strip each segment; drop segments that are empty after stripping (e.g. two tags
  back to back with no text between them) — they produce no chunk and no generation
  call.
- Do not strip/validate here — validation is a separate pass (§4) so the error
  message can enumerate *all* bad keys in one shot, not fail on the first.

## 4. Validation (fail-fast)

Before any `generate_audio()` call:

- Collect the set of all mood keys captured by `_MOOD_TAG_RE` (regardless of whether
  their segment ended up empty).
- Diff against `MOOD_PRESETS.keys()`.
- Any unknown key → write `ERROR: unknown mood 'xxx' in --stdin text` to stderr
  (one line per bad key, matching the existing `ERROR: ...` stdout/stderr contract
  documented in CLAUDE.md), still emit the trailing `TIMING ...` line, exit non-zero.
  **No audio is generated** — this check runs before the chunk/generate loop starts.
- Files with zero tags skip this pass entirely (existing single-instruct behavior,
  byte-for-byte unchanged).

## 5. Integration with `--stdin` flow (new job-list dispatch)

In `main()`'s `--stdin` branch:

1. Read file text (unchanged).
2. `segments = split_mood_segments(text)`.
3. Validate all mood keys (§4); exit on failure before touching the model/daemon.
4. Build a flat ordered job list: for each `(mood_key, segment_text)` in `segments`,
   `chunk_text(segment_text)` (existing function, unchanged), pair every resulting
   chunk with `instruct = resolve_instruct(mood_key, None, voice_default)` for that
   segment (`mood_key=None` falls through the existing priority chain — per-voice
   default file, then `MOOD_PRESETS["default"]`, exactly as today).
5. **If the job list has exactly one job** (no tags, or one tag covering everything,
   and the text still fits in one `chunk_text()` piece): behavior is **byte-for-byte
   identical to today** — single `_try_daemon()`/in-process `generate_audio()` call,
   no concat, no temp dir. This is the common case and must not regress.
6. **If the job list has 2+ jobs** (this is the new path — reactivates what `_run()`'s
   dead `multi` branch attempted, generalized to per-job `instruct` and per-job daemon
   dispatch, which the old dead branch never did):
   - For each job, try `_try_daemon(chunk, part_path, instruct, voice, fmt="wav",
     lang=lang)` first (daemon already accepts `instruct` per request — no protocol
     change); fall back to in-process `generate_audio()` only if the daemon isn't up,
     loading the model once and reusing it across the remaining jobs in the loop (not
     reloading per job).
   - Write each job's audio to a temp part file (`tempfile.mkdtemp`, same pattern as
     the current dead `multi` branch: `qwen_clone_tts.py:252-295`).
   - Any job failing (daemon error, missing output) aborts the whole run — no partial
     file playback, matching the fail-fast validation posture from §4. Clean up the
     temp dir either way.
   - `ffmpeg -f concat` all part files into `out_path` (reuse the exact ffmpeg
     invocation at `qwen_clone_tts.py:284-288`), then continue to the existing
     mp3-conversion / `OK <path>` / `TIMING ...` output as today.
7. This job-list dispatch is scoped to the `--stdin` mood-tag path only. The plain
   `--text`/`--instruct`/`--mood` CLI branch and `_run()`'s single-call path are
   **not touched** — `MAX_CHARS` still hard-rejects there exactly as today. `_run()`'s
   existing dead `multi` branch is superseded/removed by this new job-list dispatch
   rather than kept as a second, still-unused code path (see §7 risk about avoiding
   two versions of the same concat logic).

Files with no `[mood:xxx]` tag anywhere still produce exactly one job — step 5 above
is the guarantee that untagged `--stdin` calls are unaffected.

## 6. Testing

`test_qwen_clone_tts.py` — unit tests for `split_mood_segments()` and the validation
pass, no model/daemon involved:

- No tag at all → single segment, `mood_key=None`, text unchanged.
- Single tag at the very start covering the whole file.
- Multiple tags interleaved with text, alternating moods.
- Two tags back to back with no text between → the empty segment is dropped, no
  phantom chunk/generate call.
- Unknown mood key → validation fails, function/CLI path raises/exits before any
  generation is attempted (assert no `generate_audio` call, not just "returns
  something falsy").
- Whitespace-only segment (tag immediately followed by only spaces/newlines then
  next tag) → dropped, same as the back-to-back case.

Manual validation (recorded in the ticket's `### Validation`):
- `--stdin` file with no tags → `OK <path>`, audio identical in tone to pre-change.
- `--stdin` file with 2+ mood tags → listen, confirm tone actually shifts per segment.
- `--stdin` file with a typo'd mood key → `ERROR: unknown mood '...'`, non-zero exit,
  zero `outputs/` files written.

## 7. Risks

- **Scope grew mid-design**: initial draft assumed the multi-chunk/concat mechanism
  was reusable as-is; code inspection showed it's dead (`multi = False` hardcoded)
  and gated off intentionally per `CLAUDE.md`. User explicitly approved reactivating
  it (§1), scoped to `--stdin` jobs with 2+ segments only (§5) — not a blanket
  re-enable of long-text chunking for `--text`/`--mood` or single-segment `--stdin`.
- Contained to the `--stdin` code path in `qwen_clone_tts.py` plus new pure-function
  unit tests. No daemon protocol change (confirmed `handle_request()` already takes
  `instruct` per request), no cache-key change, no change to the plain `--text`
  CLI branch's `MAX_CHARS` behavior.
- Behavior change for `--stdin` callers is opt-in for the *tagging* — a file needs
  `[mood:xxx]` to produce 2+ jobs; untagged single-job files are provably identical
  to today (§5 step 5). But this ticket does remove dead code (`_run()`'s `multi`
  branch, §5 step 7) — a `git blame`/history check before deleting it, to confirm no
  other in-flight branch depends on it, is part of the implementation plan.
- Daemon-per-job dispatch (§5 step 6) means a mood-tagged `--stdin` call with N
  segments makes N round-trips to the daemon (or N in-process generations sharing one
  loaded model) instead of 1 — proportionally slower wall-clock for multi-mood files.
  Expected and acceptable; not a regression since untagged calls stay at 1 call.
- If Hermes's actual output ever starts containing literal `[...]` text (contrary to
  the "no brackets today" assumption in §2.1), those would now misparse as mood tags.
  Accepted as a non-issue per user confirmation; revisit the delimiter choice only if
  that assumption changes.
