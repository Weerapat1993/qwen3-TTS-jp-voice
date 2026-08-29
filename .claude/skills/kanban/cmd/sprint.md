# Sprint Close

For `/kanban sprint close` or `/kanban sprint close --name=splint-X`:

1. Read `obsidian/kanban/work-kanban-board.md` to collect all entries in `## DONE` and `## CLOSED`.
2. If neither section has any entries, report that there is nothing to archive and stop.
3. Determine the new splint file name:
   - If `--name=` is provided, use that value (e.g. `splint-3`).
   - Otherwise, scan existing `obsidian/kanban/splint-*.md` files, find the highest number, and increment by 1.
4. Create `obsidian/kanban/splint-X-kanban-board.md` with only the done and closed entries from step 1. Use the minimal splint format described in **Board Architecture**.
5. Remove the archived ticket entries from `## DONE` and `## CLOSED` in `work-kanban-board.md`. Leave all other sections (`## BACKLOG`, `## PLAN`, `## TODO`, `## INPROGRESS`, `## REVIEW`) untouched — unfinished tickets carry forward automatically.
6. Do not move or rename any ticket files in `obsidian/kanban/tasks/`.
7. Do not change `Status:` inside any ticket file.
8. Run the project's `sync-progress` command if one is defined. Report any failure without reverting the archive.
9. Report: the new splint file created, which tickets were archived, and which tickets remain on the active board.
