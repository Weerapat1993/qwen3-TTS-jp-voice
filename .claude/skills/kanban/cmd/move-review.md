# Move To Review

For `/kanban move-review WORK-XXXX`:

1. Confirm implementation and required validation have passed.
2. Add or update `### Review Notes` in the ticket file.
3. Move the ticket entry to the `## REVIEW` section of `obsidian/kanban/work-kanban-board.md`.
4. Change `Status:` to `Review` in the ticket body **and** update `status: review` in the YAML frontmatter block at the top of the ticket file. Both must be updated together in the same edit.
5. Sync based on provider:
    - `local` or unset: run the project's `sync-ticket` command for `WORK-XXXX` if defined. Report any failure but do not revert.
    - `notion`: resolve `notion_page_id` the same way as `/kanban start` step 11 (read frontmatter, fall back to `ntn api v1/search`). If resolved, call `ntn api v1/pages/{notion_page_id} -X PATCH -d '{"properties": {"Status": {"status": {"id": "{notionStatusMap.review}"}}}}'`. If `notionStatusMap.review` is missing or no page was found, skip and print the matching one-line warning. Report any other failure but do not revert local state.
    - `lark`: skip local sync; use Lark commands in the next step instead.
6. Create the pull request based on provider:
   - `local`: run the project's `create-pr` command for `WORK-XXXX`. If the project defines none, fall back to `gh pr create` as described for `notion`. Report any failure without reverting.
   - `notion`: run `gh pr create` using the GitHub CLI. Use `--base main` (or the repo's default branch), title `{TICKET}: {ticket title}` (without emoji), and a body that includes the ticket summary, acceptance criteria, and a link to `obsidian/kanban/tasks/WORK-XXXX.md`. The Notion data source backing this board has no PR-url property, so do not attempt to link the PR URL on the Notion card — the Status PATCH in step 5 is the only Notion write for this command. If `gh` is not installed or not authenticated, report the error and skip PR creation without reverting local state.
   - `lark`: if `gh` is available and the repo has a GitHub remote, run `gh pr create` with the same title/body format as above. Report any failure without reverting.
7. If optional Lark sync is enabled (or `KANBAN_PROVIDER=lark`), run `lark-move` for `WORK-XXXX` with target `review` after the local board and ticket status are updated. Report any Lark failure without reverting the local move.
