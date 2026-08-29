# Start Ticket

For `/kanban start WORK-XXXX`:

1. Read the ticket file.
2. Read `prd.md` when the ticket affects product scope, public pages, admin-managed website content, SEO, structured data, content quality, or user-facing behavior.
3. Read referenced specs, context files, and acceptance criteria.
4. If the ticket conflicts with the PRD and the conflict is not approved by the user, add or update `### Open Questions` and stop before moving to `In Progress`.
5. If the ticket has `Status: Plan` and `### Implementation Plan`, continue directly without invoking `writing-plans` again.
6. If the ticket has `Status: Backlog`, it may skip `Plan` and move directly to `In Progress` when all of these are true:
   - acceptance criteria are clear
   - required context/spec references are available or unnecessary
   - there are no unresolved `### Open Questions` or blocking notes
   - the work is small, low-risk, and does not require `writing-plans` under the Plan Ticket recommendation rules
7. If the backlog ticket does not satisfy every skip condition, run the Plan Ticket flow first and stop if planning creates new open questions.
8. Move the ticket entry to the `## INPROGRESS` section of `obsidian/kanban/work-kanban-board.md`.
9. Change `Status:` to `In Progress` in the ticket body **and** update `status: inprogress` in the YAML frontmatter block at the top of the ticket file. Both must be updated together in the same edit.
10. **REQUIRED: Complete steps 8–9 and confirm both files are saved before proceeding to any implementation step. Do not invoke any implementation skill or write any code until the board entry has moved and `Status:` reads `In Progress`.**
11. Sync based on provider:
    - `local` or unset: run the project's `sync-ticket` command for `WORK-XXXX` if defined. Report any failure but do not revert.
    - `notion`: read `notion_page_id` from the ticket's YAML frontmatter. If absent, resolve it first: `ntn api v1/search -d '{"query":"{TICKET}:"}'`, find the result whose `object` is `page` and whose title starts with `{TICKET}:`, and store its `id` as `notion_page_id` in the frontmatter (same edit as the status change below). If no match is found, skip this step, print `Notion sync skipped: no Notion page found for {TICKET}`, and continue. Otherwise call `ntn api v1/pages/{notion_page_id} -X PATCH -d '{"properties": {"Status": {"status": {"id": "{notionStatusMap.inprogress}"}}}}'`. If `notionStatusMap.inprogress` is missing, skip this step and print `Notion sync skipped: no status mapping for "inprogress"`. Report any other failure but do not revert local state.
    - `lark`: skip local sync; use Lark commands in the next step instead.
12. If optional Lark sync is enabled (or `KANBAN_PROVIDER=lark`), run `lark-move` for `WORK-XXXX` with target `inprogress` immediately after the local board and ticket status are updated, before implementation work begins. Report any Lark failure without reverting the local move.
13. If the ticket is a bug report or regression, use the `debug-mantra` skill before proposing or implementing a fix. If the user asks to skip the recital, still apply its reproduce -> trace -> falsify -> breadcrumb workflow silently.
14. After implementation, run the project's `post-implementation` steps described in **Local Provider Commands** — for example schema migration or data seeding commands when the ticket changed those files. Skip when the project defines none.
15. Run the ticket's required validation after any `post-implementation` steps that apply.
16. After implementation and validation, report the result, whether the ticket appears ready for review, and any deployment commands the project's **Local Provider Commands** section requires for this change. Mention explicitly when no deployment command is required.
17. Do not move the ticket to Review automatically during `start`, even when implementation and validation pass.
18. Do not run `lark-move` with target `review` during `start`.
22. Wait for an explicit `/kanban move-review WORK-XXXX` command before adding `Review Notes`, moving the ticket entry to the `## REVIEW` section, changing `Status:` to `Review`, or syncing Lark to `review`.

Do not invoke `writing-plans` again during `start` when the ticket already has `Status: Plan` and `### Implementation Plan`.

If acceptance criteria or required context is missing, stop and ask for the missing information.
