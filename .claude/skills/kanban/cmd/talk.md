# Talk

For `/kanban talk ...`, accept any of these inputs:

```txt
/kanban talk WORK-XXXX
/kanban talk WORK-XXXX - WORK-YYYY
/kanban talk WORK-XXXX, WORK-YYYY, WORK-ZZZZ
/kanban talk WORK-XXXX --lang=en
```

Language options:

- Default output language is Thai for the generated marketing ticket content.
- Use `--lang=en`, `--lang=english`, `--language=en`, or `--language=english` to generate the marketing ticket content in English.
- Keep fixed ticket IDs, file paths, `Status:`, section labels, route names, commands, and technical identifiers unchanged regardless of output language.

Parse ticket targets as follows:

- A single ticket target processes that one ticket.
- A range target such as `WORK-1021 - WORK-1038` processes every ticket inclusively, in numeric order from the first ID to the second ID.
- A comma-separated target such as `WORK-1021, WORK-1028, WORK-1038` processes tickets in the exact queue order provided.
- Combined comma and range syntax is allowed, for example `WORK-1021 - WORK-1023, WORK-1038`; expand each range in place and preserve the overall queue order.
- If the same ticket appears more than once after expansion, process it only once at its first position and report that duplicates were skipped.

For each ticket in the resolved queue:

1. Use the `management-talk` skill.
2. Read `obsidian/kanban/tasks/WORK-XXXX.md`.
3. Follow the `management-talk` required context rules, including reading `prd.md` when the ticket affects public pages, website content, SEO, AI readability, admin-managed content, product scope, or brand behavior.
4. Create or update `obsidian/kanban/tasks/marketing-tickets/WORK-XXXX.md` using the `management-talk` output format.
5. Do not move the ticket between board sections.
6. Do not change `Status:` in the source ticket.
7. Continue to the next ticket even if one ticket has open questions or cannot be translated, unless the failure prevents safely interpreting the remaining queue.

After processing the queue, report:

- the resolved ticket order
- created or updated marketing ticket paths
- skipped duplicates, missing source tickets, and open questions that prevented a complete translation
