# API Get Backlog

For `/kanban api get-backlog`:

1. Read config from `.kanban.json` or environment variables. Require `notionDataSourceId` (or `NOTION_DATA_SOURCE_ID`) and a working `ntn` auth session. If either is missing, stop with:

   ```
   KANBAN_API error: notionDataSourceId ไม่ได้ตั้งค่า หรือ ntn ยังไม่ login
   ตั้งค่าใน .kanban.json หรือ environment variables แล้วลองใหม่
   ```

2. Scan all files in `obsidian/kanban/specs/backlog/` (if the directory exists). For each file, read its content and parse lines matching `Card ID: {id}` — collect all IDs into a `skip_ids` array. If the directory does not exist, `skip_ids` is empty.

3. Query the Backlog column with:
   ```bash
   ntn api v1/data_sources/{notionDataSourceId}/query -X POST -d '{
     "filter": {"property": "Status", "status": {"equals": "Backlog"}}
   }'
   ```
   If `notionStatusMap.backlog` has no entry, stop with `KANBAN_API error: notionStatusMap.backlog ไม่ได้ตั้งค่า`.

4. Handle API errors:
   - 401 / 403: stop with "ntn ไม่ได้ authenticate หรือไม่มีสิทธิ์เข้าถึง data source นี้"
   - 404: stop with "Notion data source not found"
   - Network / timeout: stop with the error message
   - Any other non-2xx: stop with the status code and message

5. If `obsidian/kanban/specs/backlog/` does not exist, create it before writing files. If creation fails (permission error), stop with the OS error.

6. For each page in the query response's `results` array:
   - The page's `id` is the card id. If `id` is already in `skip_ids`, count as skipped, do not write.
   - Otherwise extract the title from `properties.Name.title[].plain_text` (joined) and derive `filename` as `{title-slug}.md` (lowercase, spaces to hyphens, strip characters outside `[a-z0-9-]`).
   - Write `obsidian/kanban/specs/backlog/{filename}` using the content format below.

7. Report results regardless of whether any new files were written:
   - When new files exist: `kanban api get-backlog: exported N new, skipped M\nFiles written to obsidian/kanban/specs/backlog/`
   - When no new files: `kanban api get-backlog: ไม่มี card ใหม่ — skipped M card ที่มีอยู่แล้ว`

**Content format** written for each new card:
```md
# {title}

Card ID: {notion page id}
Created At: {page's created_time field}

## รายละเอียด
{page's body content, if any — read via `ntn pages get {page id}`; otherwise leave this section empty}
```

**Rules:**
- Never use project-local CLI commands — this command must work in external projects that have no local backend.
- Derive `filename` from the title as described in step 6 — do not depend on a server-provided filename field (Notion has none).
- Write only pages currently in the Backlog status.
- The `skip_ids` deduplication (matched against the Notion page id) prevents rewriting existing cards.
- `obsidian/kanban/specs/backlog/` is auto-created if absent.
