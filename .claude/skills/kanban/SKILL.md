---
name: kanban
description: Use when the user invokes /kanban or asks to create, start, move, review, complete, close, or check project tickets using obsidian/kanban/context/kanban-flow.md, obsidian/kanban/work-kanban-board.md, and obsidian/kanban/tasks/WORK-XXXX.md ticket files. Supports creating tickets from a Markdown marketing or product requirement file.
metadata:
  short-description: Manage project Kanban tickets
---

# Kanban

Use this skill to operate the repo's local ticket workflow.

Per-command instructions live in separate files under `cmd/`. When a command runs, read ONLY its `cmd/{name}.md` file — do not read the others. This keeps context small.

Always read `obsidian/kanban/context/kanban-flow.md` before changing ticket files. That file is the source of truth for board structure, gates, status movement, and required notes.

Use `prd.md` as the product-level source of truth for project scope, product goals, target users, non-goals, success metrics, and SEO/AI requirements. Read it before creating tickets, planning tickets, starting feature work from backlog, or reviewing product-facing / SEO-impacting tickets.

## Configuration

Before executing any command, read config from `.kanban.json` in the project root (if it exists):

```json
{
  "provider": "local",
  "notionDataSourceId": "<your Notion data_source id>",
  "notionStatusMap": {
    "backlog": "<option id>",
    "todo": "<option id>",
    "plan": "<option id>",
    "inprogress": "<option id>",
    "review": "<option id>",
    "done": "<option id>"
  }
}
```

Config can also be provided through environment variables (take precedence over `.kanban.json`):

- `KANBAN_PROVIDER` — `local`, `notion`, or `lark`
- `NOTION_DATA_SOURCE_ID` — the Notion data_source id backing the board

**Provider routing:**

- `local` (default): use local `.md` files for all board operations. When the project defines local sync commands, run them — see **Local Provider Commands** in `obsidian/kanban/context/kanban-flow.md`. Skip the step silently when the project defines no command for that operation.
- `notion`: route board writes through the Notion REST API via the `ntn` CLI (`ntn api ...`). Requires `notionDataSourceId` (or `NOTION_DATA_SOURCE_ID`) and `notionStatusMap`, plus a working `ntn` auth session (`NOTION_API_TOKEN` env var or prior `ntn login`). Sync is one-way: local `.md` files are always the source of truth; nothing is ever pulled from Notion to overwrite a local file. If a target status has no entry in `notionStatusMap`, skip the Notion API call for that step, print a one-line warning (`Notion sync skipped: no status mapping for "{status}"`), and continue the rest of the command — do not fail the local flow.
- `lark`: route ticket operations through the Lark task API. Requires `lark-cli` to be installed and authenticated, plus the project's Lark commands listed in **Local Provider Commands**.

**Operation names:** this skill refers to project commands by generic operation name (`import-ticket`, `sync-ticket`, `create-pr`, `sync-progress`, `post-implementation`, `lark-create`, `lark-rename`, `lark-move`, `lark-help`). Each project maps those names to its own CLI in the **Local Provider Commands** section of `obsidian/kanban/context/kanban-flow.md`. Never assume a framework-specific command exists.

**Missing config error — show this message and stop when `notion` is selected but `notionDataSourceId`/`NOTION_DATA_SOURCE_ID` is absent:**

```txt
KANBAN_PROVIDER is set to "notion" but required config is missing.

Add a .kanban.json file to your project root:

{
  "provider": "notion",
  "notionDataSourceId": "<your Notion data_source id>",
  "notionStatusMap": {
    "backlog": "<option id>",
    "todo": "<option id>",
    "plan": "<option id>",
    "inprogress": "<option id>",
    "review": "<option id>",
    "done": "<option id>"
  }
}

Or set: export KANBAN_PROVIDER=notion; export NOTION_DATA_SOURCE_ID=<id>

Find data_source id + status option ids with:
  ntn api v1/search -d '{"query":"<board name>"}'
  ntn api v1/data_sources/<data_source_id>
```

**Missing config error — show this message and stop when `notion` is selected but `ntn` has no working auth session:**

```txt
KANBAN_PROVIDER is set to "notion" but the `ntn` CLI is not authenticated.

Set NOTION_API_TOKEN, or run:
  ntn login
```

**Missing config error — show this message and stop when `lark` is selected but `lark-cli` is missing:**

```txt
KANBAN_PROVIDER is set to "lark" but lark-cli is not installed or authenticated.

Install and authenticate:
  lark-cli auth login --scope "task:task:write task:tasklist:read task:section:read task:section:write"

Also ensure LARK_TASKLIST_GUID is set in your project environment.
```

If `.kanban.json` is missing and no environment variables are set, default to `provider: local` — do not error.

## Response Language

Respond to the user in Thai by default for every Kanban interaction, including help output, status summaries, review results, blockers, implementation updates, and completion notes.

Use another language only when the user explicitly asks for it. Keep fixed workflow keywords, file paths, commands, ticket IDs, status values, and verdict values exactly as written in the flow, for example `Status:`, `PASS`, `NEEDS FIX`, `BLOCKED`, `Review Notes`, and `Done Notes`.

## Command Patterns

Treat these user messages as Kanban commands:

```txt
/kanban create WORK-XXXX
/kanban create WORK-XXXX from path/to/requirement.md
/kanban plan WORK-XXXX
/kanban start WORK-XXXX
/kanban move-review WORK-XXXX
/kanban review WORK-XXXX
/kanban done WORK-XXXX
/kanban close WORK-XXXX
/kanban status WORK-XXXX
/kanban sync
/kanban sync WORK-XXXX
/kanban talk WORK-XXXX
/kanban talk WORK-XXXX - WORK-YYYY
/kanban talk WORK-XXXX, WORK-YYYY, WORK-ZZZZ
/kanban talk WORK-XXXX --lang=en
/kanban lark status
/kanban lark enable
/kanban lark disable
/kanban lark sync WORK-XXXX
/kanban sprint close
/kanban sprint close --name=splint-3
/kanban api get-backlog
/kanban help
```

Also trigger this skill for natural language requests such as "ทำ Ticket WORK-XXXX", "สร้าง ticket จาก requirement file", or "ย้าย ticket ไป done".

## Command Dispatcher

Route each command to its file and read ONLY that file (plus always apply **Core Rules** and **Obsidian Properties** below):

| Command | File to read |
|---|---|
| `/kanban help` | `cmd/help.md` |
| `/kanban create ...` | `cmd/create.md` |
| `/kanban plan ...` | `cmd/plan.md` |
| `/kanban start ...` | `cmd/start.md` |
| `/kanban move-review ...` | `cmd/move-review.md` |
| `/kanban review ...` | `cmd/review.md` |
| `/kanban done ...` | `cmd/done.md` |
| `/kanban close ...` | `cmd/close.md` |
| `/kanban sprint close ...` | `cmd/sprint.md` |
| `/kanban sync ...` | `cmd/sync.md` |
| `/kanban status ...` | `cmd/status.md` |
| `/kanban talk ...` | `cmd/talk.md` |
| `/kanban api get-backlog` | `cmd/api-get-backlog.md` |
| `/kanban lark ...` | `cmd/lark.md` |

## Board Architecture

This project uses two types of board files:

**Active board** — `obsidian/kanban/work-kanban-board.md`
- The single living board for all current work.
- Ticket entries move between `## COLUMN` sections as work progresses.
- Always read this file to find where a ticket currently lives.

**Sprint archive boards** — `obsidian/kanban/splint-X-kanban-board.md`
- Immutable records of closed sprints. Do not modify these files during normal ticket operations.
- Each splint board shows only the tickets that were **completed or closed** during that sprint (`## DONE` and `## CLOSED` sections).
- Tickets that were not finished when the sprint closed are carried forward to `work-kanban-board.md ## BACKLOG`.
- These files exist as historical logs — they answer "what did sprint N deliver?" not "what is in progress now?"

When the user asks to **close a sprint** or **start a new sprint**:

1. Create a new `obsidian/kanban/splint-X-kanban-board.md` (increment X from the latest existing splint number).
2. Copy only the `## DONE` and `## CLOSED` ticket entries from `work-kanban-board.md` into the new splint file.
3. Remove from `work-kanban-board.md` any tickets that were moved into the new splint archive.
4. Leave unfinished tickets (`## BACKLOG`, `## PLAN`, `## INPROGRESS`, `## REVIEW`) in `work-kanban-board.md` — they carry forward automatically.
5. Do not move or rename ticket files in `obsidian/kanban/tasks/` — only board entries change.

The splint file format is minimal (only done/closed sections):

```md
---

kanban-plugin: board

---

## DONE

- [WORK-XXXX](tasks/WORK-XXXX.md): Ticket title


## CLOSED

- [WORK-XXXX](tasks/WORK-XXXX.md): Ticket title

%% kanban:settings
{"kanban-plugin":"board","list-collapse":[false,false]}
%%
```

## Core Rules

- Ticket files live at `obsidian/kanban/tasks/WORK-XXXX.md`.
- The board is a single file at `obsidian/kanban/work-kanban-board.md` with `## COLUMN` sections: `## BACKLOG`, `## PLAN`, `## TODO`, `## INPROGRESS`, `## REVIEW`, `## DONE`, `## CLOSED`.
- Move status by moving the ticket entry between sections in the board file and updating `Status:` inside the ticket file.
- In the first ticket heading, add a type emoji before the ticket ID when the ticket type can be identified: `🟢` for Feature and `🔴` for Bugfix. If the type cannot be identified, leave the emoji blank.
- Do not duplicate the same ticket entry across multiple sections of the board file.
- Do not rename or move the ticket file during normal status changes.
- Never mark a ticket done unless the gates in `obsidian/kanban/context/kanban-flow.md` are satisfied.
- If a requirement is ambiguous, add `### Open Questions` to the ticket instead of inventing risky details.

## Obsidian Properties (YAML frontmatter) rules

Applies to every ticket file you create or edit:

- Every ticket file MUST start with a YAML frontmatter block (`---` … `---`) before the first heading.
- `ticket_id`: the ticket ID (e.g. `WORK-1007`).
- `title`: plain-text ticket title without the emoji prefix.
- `type`: `feature` for Feature tickets, `bugfix` for Bugfix tickets, `chore` for internal/tooling work, or `unknown` when the type cannot be determined.
- `status`: lowercase status value — one of `backlog`, `plan`, `todo`, `inprogress`, `review`, `done`, `closed`. Keep this in sync with the `Status:` field in the ticket body whenever the status changes.
- `priority`: lowercase — `high`, `medium`, or `low`. Keep in sync with the `Priority:` field in the ticket body.
- `spec`: path to the spec file if one exists; omit this key when there is no spec.
- `lark_guid`: Lark task GUID if the ticket was linked to an existing Lark task (e.g. from a backlog spec with `Lark GUID:`); omit this key when there is no pre-existing Lark task.
- `notion_page_id`: Notion page id for this ticket's card, set the first time a `notion`-provider command creates or matches the card (e.g. `POST /v1/pages` on `/kanban create`, or a title match on `/kanban start`/`/kanban sync`); omit this key when the ticket has no Notion card yet.
- `tags`: always include `kanban/ticket` and `work`.
- When updating `Status:` in the ticket body (e.g. during `/kanban start`, `/kanban move-review`, `/kanban done`), also update the `status:` frontmatter field to match.
