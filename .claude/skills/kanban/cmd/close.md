# Close Ticket

For `/kanban close WORK-XXXX`:

1. Add or update `### Closed Notes` with the reason.
2. If closing a fixed bug that has reliable repro, known root cause, identified fix, and validation, use the `post-mortem` skill first when the root cause should be preserved.
3. Move the ticket entry to the `## CLOSED` section of `obsidian/kanban/work-kanban-board.md`.
4. Change `Status:` to `closed` in the ticket body **and** update `status: closed` in the YAML frontmatter block at the top of the ticket file. Both must be updated together in the same edit.
5. If `KANBAN_PROVIDER=notion`: resolve `notion_page_id` the same way as `/kanban start` step 11. If `notionStatusMap.closed` is not set (common — many Notion boards have no dedicated "Closed" status option), skip this step and print `Notion sync skipped: no status mapping for "closed"` — the local board/ticket status change from steps 3–4 still applies. If `notionStatusMap.closed` is set and a page was resolved, call `ntn api v1/pages/{notion_page_id} -X PATCH -d '{"properties": {"Status": {"status": {"id": "{notionStatusMap.closed}"}}}}'`. On failure, report error without reverting local state.
6. If optional Lark sync is enabled, run `lark-move` for `WORK-XXXX` with target `closed` after the local board and ticket status are updated. Report any Lark failure without reverting the local move.

Use this for canceled, obsolete, duplicate, or out-of-scope tickets.
