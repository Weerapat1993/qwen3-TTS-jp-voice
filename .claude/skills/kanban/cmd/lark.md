# Optional Lark Ticket Command Sync

Lark Ticket Command sync is optional. Local `obsidian/kanban/tasks` ticket files and the board file remain the source of truth. Lark sync must never block normal local Kanban work when the user has not installed `lark-cli`, has not authenticated, has disabled sync, or a Lark command fails.

Use `obsidian/kanban/tasks/lark-sync.json` as the small local preference file for this skill:

```json
{
  "enabled": false
}
```

If the file is missing, treat Lark sync as disabled. For `/kanban lark enable`, create or update the file with `"enabled": true`; this records that the user has confirmed they want Lark sync enabled for future commands. For `/kanban lark disable`, create or update it with `"enabled": false`. For `/kanban lark status`, report the preference, whether `lark-cli` is available, and whether project configuration appears present.

Before running any automatic Lark command:

1. Check `obsidian/kanban/tasks/lark-sync.json`.
2. If sync is disabled or the file is missing, skip all Lark work and continue the normal Kanban command.
3. If sync is enabled, do not re-check `command -v lark-cli` on every `/kanban` command; rely on the previous `/kanban lark status` / `/kanban lark enable` confirmation to reduce token usage.
4. Run the project's command for the requested Lark operation (`lark-create`, `lark-rename`, `lark-move`), as mapped in **Local Provider Commands**.
5. If the command reports that `lark-cli`, auth, or config is missing, explain setup and ask whether to disable sync or skip Lark for this command. Report failures clearly without reverting local Kanban state.

Setup guidance when `lark-cli` is missing or not authenticated:

```sh
lark-cli auth login --scope "task:task:write task:tasklist:read task:section:read task:section:write"
```

The project also needs Lark task configuration available to its runtime, including `LARK_TASKLIST_GUID` and optionally `LARK_TASK_ASSIGNEE_OPEN_ID`. Users can inspect local command usage by running the project's `lark-help` command from **Local Provider Commands**.

Status mapping for automatic move sync:

```txt
Backlog -> backlog
Todo -> todo
In Progress -> inprogress
Review -> review
Done -> done
Closed -> closed
```

Do not run `/kanban lark sync WORK-XXXX` automatically from `/kanban lark enable`. It is an explicit manual backfill command for existing local tickets that are missing from the Lark Kanban Board.

# Manual Lark Sync

For `/kanban lark sync WORK-XXXX`:

1. Read `obsidian/kanban/context/kanban-flow.md`.
2. Check `obsidian/kanban/tasks/lark-sync.json`.
3. If sync is disabled or the file is missing, report that Lark sync is disabled and ask the user to run `/kanban lark enable` before syncing.
4. Read `obsidian/kanban/tasks/WORK-XXXX.md`.
5. Find which board section in `obsidian/kanban/work-kanban-board.md` contains the ticket entry and report the current local `Status:` and board location.
6. Run the equivalent `/kanban talk WORK-XXXX` workflow to create or update `obsidian/kanban/tasks/marketing-tickets/WORK-XXXX.md`.
7. After the marketing ticket exists, run the project's `lark-create` command for `WORK-XXXX`.
8. Do not move the local board entry.
9. Do not change `Status:` in the local ticket file.
10. If the marketing ticket step or Lark create command fails, report the failure clearly without changing local Kanban state.
