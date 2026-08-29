# Done Ticket

For `/kanban done WORK-XXXX`:

1. Confirm all required gates have passed.
2. If this is a meaningful bugfix and reliable repro, known root cause, identified fix, and validation are all present, use the `post-mortem` skill before moving to Done when the root cause should be preserved.
3. Add or update `### Done Notes`, including which gates ran or were skipped and why.
4. Move the ticket entry to the `## DONE` section of `obsidian/kanban/work-kanban-board.md`.
5. Change `Status:` to `done` in the ticket body **and** update `status: done` in the YAML frontmatter block at the top of the ticket file. Both must be updated together in the same edit.
6. Sync based on provider:
    - `local` or unset: run the project's `sync-ticket` command for `WORK-XXXX` if defined, then its `sync-progress` command if defined. Report any failure but do not revert.
    - `notion`: resolve `notion_page_id` the same way as `/kanban start` step 11. If resolved, call `ntn api v1/pages/{notion_page_id} -X PATCH -d '{"properties": {"Status": {"status": {"id": "{notionStatusMap.done}"}}}}'`. If `notionStatusMap.done` is missing or no page was found, skip and print the matching one-line warning. Report any other failure but do not revert local state.
    - `lark`: skip local sync; use Lark commands in the next step instead.
7. If optional Lark sync is enabled (or `KANBAN_PROVIDER=lark`), run `lark-move` for `WORK-XXXX` with target `done` after the local board and ticket status are updated. Report any Lark failure without reverting.
