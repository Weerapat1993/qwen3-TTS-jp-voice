# Sync Tickets

For `/kanban sync` and `/kanban sync WORK-XXXX`:

**Prerequisites:** Requires `KANBAN_PROVIDER=notion` (or `provider: notion` in `.kanban.json`) with `notionDataSourceId`/`NOTION_DATA_SOURCE_ID` set and a working `ntn` auth session. If config is missing, show the setup guide from the Configuration section and stop.

**Direction:** this command is one-way, local → Notion. Local `.md` ticket files are always the source of truth. This command never downloads Notion content into a local file — it only pushes ticket title/status to Notion, creating the Notion card if one doesn't exist yet.

### Full sync: `/kanban sync`

1. Read config from `.kanban.json` or env. Show setup guide and stop if `notionDataSourceId` or `ntn` auth is missing.
2. For each ticket file in `obsidian/kanban/tasks/*.md`, in board order (walk `obsidian/kanban/work-kanban-board.md` top to bottom so status is unambiguous):
   a. Read the ticket's `ticket_id`, `title`, `status` (frontmatter) and `notion_page_id` (frontmatter, may be absent).
   b. Map the local `status` value to a Notion option id via `notionStatusMap`. If there is no entry for this status, skip this ticket, add it to the skipped list with reason `no status mapping for "{status}"`, and continue with the next ticket.
   c. If `notion_page_id` is absent, try to resolve it: `ntn api v1/search -d '{"query":"{ticket_id}:"}'`, matching a `page` result whose title starts with `{ticket_id}:`. If found, store it in the ticket's frontmatter as `notion_page_id`.
   d. If still no `notion_page_id` (no existing card and none matched), create one: `ntn api v1/pages -d '{"parent": {"type": "data_source_id", "data_source_id": "{notionDataSourceId}"}, "properties": {"Name": {"title": [{"text": {"content": "{ticket_id}: {title}"}}]}, "Status": {"status": {"id": "{mapped_status_id}"}}}}'`. Store the returned `id` as `notion_page_id` in the ticket's frontmatter.
   e. If `notion_page_id` was already known (from frontmatter or resolved in step c), update it: `ntn api v1/pages/{notion_page_id} -X PATCH -d '{"properties": {"Name": {"title": [{"text": {"content": "{ticket_id}: {title}"}}]}, "Status": {"status": {"id": "{mapped_status_id}"}}}}'`.
   f. On any per-ticket API failure, record the ticket in the failed list with the error and continue with the remaining tickets — do not let one failure stop the whole sync.
3. Report a summary: tickets created on Notion, tickets updated on Notion, tickets skipped (no status mapping), tickets failed (with reasons).

### Single ticket sync: `/kanban sync WORK-XXXX`

1. Read config. Show setup guide and stop if config is missing.
2. Read `obsidian/kanban/tasks/WORK-XXXX.md`'s `ticket_id`, `title`, `status`, `notion_page_id`.
3. Follow steps 2b–2f from the full sync above for this single ticket.
4. Report: created, updated, skipped (with reason), or failed (with reason).
