# Help

For `/kanban help`, show a concise command reference and examples without changing any files.

Include these commands:

```txt
/kanban help
  Show basic commands and usage examples.

/kanban create WORK-XXXX
  Create a new ticket file and add it to todo.

/kanban create WORK-XXXX from path/to/requirement.md
  Convert a Markdown marketing/product requirement file into a ticket.

/kanban status WORK-XXXX
  Show ticket status, board location, source/spec references, and blockers.

/kanban sync
  Push all local tickets' title/status to the Notion board (creates missing cards, updates changed ones). One-way: local .md stays the source of truth.

/kanban sync WORK-XXXX
  Push a single ticket's title/status to the Notion board.

/kanban talk WORK-XXXX
  Use the management-talk skill to rewrite the ticket for marketing, content, SEO, or management readers.

/kanban talk WORK-XXXX - WORK-YYYY
  Rewrite an inclusive ticket range in numeric order from the first ID to the second ID.

/kanban talk WORK-XXXX, WORK-YYYY, WORK-ZZZZ
  Rewrite multiple tickets in the exact queue order provided.

/kanban talk WORK-XXXX --lang=en
  Rewrite marketing tickets in English instead of the default Thai.

/kanban lark status
  Show whether optional Lark Ticket Command sync is enabled and whether local setup appears ready.

/kanban lark enable
  Enable optional Lark Ticket Command sync for future kanban create/status-move commands.

/kanban lark disable
  Disable optional Lark Ticket Command sync and continue using only local Markdown tickets.

/kanban lark sync WORK-XXXX
  Backfill an existing local ticket into Lark without moving its local board status.

/kanban plan WORK-XXXX
  Analyze planning needs, ask Yes/No to continue, then plan and move the ticket to Plan.

/kanban start WORK-XXXX
  Start a ticket, move it to in-progress, and begin implementation. Backlog tickets may skip Plan when ready.

/kanban move-review WORK-XXXX
  Add review notes and move the ticket to review after validation passes.

/kanban review WORK-XXXX
  Run the final review gate, using scrutinize when risk warrants it, and report PASS, NEEDS FIX, or BLOCKED.

/kanban done WORK-XXXX
  Move the ticket to done after all required gates pass. For meaningful bugfixes, run post-mortem first when root cause should be preserved.

/kanban close WORK-XXXX
  Close a canceled, duplicate, obsolete, or out-of-scope ticket. Preserve post-mortem details first when closing a fixed bug with known root cause.

/kanban sprint close
  Close the current sprint: archive done/closed tickets into a new splint-X file, carry forward unfinished tickets in work-kanban-board.md.

/kanban sprint close --name=splint-3
  Same as above but use a specific name for the new sprint archive file.

/kanban api get-backlog
  Pull Backlog cards from the Notion board and write them as .md files into obsidian/kanban/specs/backlog/.
  Requires notionDataSourceId to be configured and ntn to be authenticated.
```

Also include two short examples:

```txt
/kanban create WORK-1012 from prd.md
/kanban plan WORK-1012
/kanban start WORK-1012
```
