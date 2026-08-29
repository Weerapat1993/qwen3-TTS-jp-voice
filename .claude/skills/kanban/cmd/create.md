# Create Ticket

For `/kanban create WORK-XXXX`:

1. Read `obsidian/kanban/context/kanban-flow.md`.
2. Read `prd.md` unless the ticket is purely internal tooling with no product, content, admin, or SEO impact.
3. If a source file is provided, read it and convert it into implementation-ready ticket requirements.
4. Align the ticket scope, non-goals, acceptance criteria, and validation with the PRD. If the request conflicts with the PRD, add `### Open Questions` and ask whether to update the PRD or treat the request as an exception.
5. Create `obsidian/kanban/tasks/WORK-XXXX.md`.
6. Add the ticket entry to the `## TODO` section of `obsidian/kanban/work-kanban-board.md`.
7. Keep the board entry format from the flow document.
8. Sync the new card based on provider:
   - `local` or unset: run the project's `import-ticket` command for `WORK-XXXX`. Report any failure but keep the local ticket in Todo. Skip when the project defines no such command.
   - `notion`: create the card with `ntn api v1/pages -d '<json>'` where `<json>` is:
     ```json
     {
       "parent": {"type": "data_source_id", "data_source_id": "{notionDataSourceId}"},
       "properties": {
         "Name": {"title": [{"text": {"content": "{TICKET}: {title}"}}]},
         "Status": {"status": {"id": "{notionStatusMap.todo}"}}
       }
     }
     ```
     Use plain ticket ID and title without emoji. On success, the response's top-level `id` field is the Notion page id — store it as `notion_page_id: {id}` in the ticket file's YAML frontmatter (same edit as the rest of ticket creation). If `notionStatusMap.todo` is missing, skip this step, print `Notion sync skipped: no status mapping for "todo"`, and keep the local ticket in Todo. Report any other failure but keep the local ticket in Todo and do not revert local state.

     After the page is created, populate its body with the ticket's `### Summary` and `### Acceptance Criteria` sections so the card is readable without opening the local file. Run `ntn api v1/blocks/{notion_page_id}/children -d '<json>'` where `<json>` is:
     ```json
     {
       "children": [
         {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "Summary"}}]}},
         {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "{summary text}"}}]}},
         {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"text": {"content": "Acceptance Criteria"}}]}},
         {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"text": {"content": "{AC line}"}}]}}
       ]
     }
     ```
     Take `{summary text}` verbatim from the ticket's `### Summary` section (join multiple paragraphs as separate `paragraph` blocks). Add one `bulleted_list_item` block per line under `### Acceptance Criteria`. If either section is missing or empty in the ticket, skip that section's blocks. If this call fails, report it but do not revert the page created in the previous step.
9. If optional Lark sync is enabled:
   a. Check whether the source spec file contains a `Lark GUID:` line (e.g. `Lark GUID: \`0a42bd30-b84b-4811-a596-22d5a84bb1c0\``). Extract the GUID value (strip backticks).
   b. **If the spec has a Lark GUID** — a Lark task already exists. Do NOT run `lark-create`. Instead:
      - Store `lark_guid: <GUID>` in the YAML frontmatter of the ticket file.
      - Run `lark-rename` for `WORK-XXXX` with the task GUID to set the title to the standard format.
      - Run `lark-move` for `WORK-XXXX` with target `todo` to move the task to the todo section.
   c. **If the spec has no Lark GUID** — run the equivalent `/kanban talk WORK-XXXX` workflow to create or update `obsidian/kanban/tasks/marketing-tickets/WORK-XXXX.md`. After the marketing ticket exists, run `lark-create` for `WORK-XXXX`. If the Lark task was created, run `lark-rename` to set the title format, then `lark-move` with target `todo`.
10. If any Lark command fails, report the failure clearly and keep the local ticket in Todo.

Ticket content should usually include:

```md
---
ticket_id: WORK-XXXX
title: Ticket title
type: feature
status: todo
priority: medium
spec: path/to/spec.md
tags:
  - kanban/ticket
  - work
---

## 🟢 WORK-XXXX: Ticket title

Status: Todo
Priority: Medium
Source: `path/to/source.md`

### Summary
...

### Context
...

### Scope
- ...

### Acceptance Criteria
- ...

### Validation
- ...
```

Use `## 🔴 WORK-XXXX: Ticket title` for Bugfix tickets. If the ticket type is unclear, use `## WORK-XXXX: Ticket title` without an emoji.

When converting a marketing or product requirement file:

- Summarize the business intent into implementation language.
- Convert marketing goals into observable acceptance criteria.
- Preserve important brand, SEO, compliance, content, and conversion requirements.
- Split unrelated work into separate proposed tickets if one source file contains multiple independent features.
- Add SEO validation when the ticket affects public pages, visible copy, metadata, structured data, internal links, or content quality.
- Avoid copying a long requirement file verbatim into the ticket.
