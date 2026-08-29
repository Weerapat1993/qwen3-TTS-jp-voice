# Plan Ticket

For `/kanban plan WORK-XXXX`:

1. Read `obsidian/kanban/context/kanban-flow.md`.
2. Read the ticket file.
3. Read `prd.md` when the ticket affects product scope, public pages, admin-managed website content, SEO, structured data, content quality, or user-facing behavior.
4. Read referenced specs, context files, acceptance criteria, and validation requirements.
5. Before changing any files, show a short pre-plan assessment:
   - ticket status and current board section
   - whether `brainstorming` is recommended before writing the plan
   - the reason for the `brainstorming` recommendation
   - whether `writing-plans` is recommended for this ticket
   - the reason for the recommendation
   - whether the ticket aligns with `prd.md`, when PRD context applies
   - what will change if planning continues
6. Ask the user with a Yes/No menu whether to continue planning.
   - Use `request_user_input` when available.
   - Label the recommended option `Yes (Recommended)` when planning should continue.
   - If `request_user_input` is unavailable, ask for a plain `Yes` or `No` response and wait.
7. If the user chooses `No`, stop without changing the ticket file or board file.
8. If required context or acceptance criteria are missing, or the ticket conflicts with the PRD and the conflict is not approved by the user, add or update `### Open Questions` in the ticket and stop without moving the ticket to Plan.
9. If the assessment recommends `brainstorming`, use the `brainstorming` skill as a pre-plan gate to clarify scope, split unrelated work, choose the approach, or resolve risky decisions before writing `### Implementation Plan`.
10. If `brainstorming` surfaces unresolved questions, add or update `### Open Questions` in the ticket and stop without moving the ticket to Plan.
11. If the assessment recommends `writing-plans`, use the `writing-plans` skill to create the implementation plan after the `brainstorming` gate is resolved.
12. After `writing-plans` returns, ask the user: **"Did you choose to execute the plan (Subagent-Driven or Inline Execution) during writing-plans?"** with a Yes/No menu. This determines whether implementation already happened and which status to assign.
    - If the user answers **Yes** (execution happened): set target status to `In Progress` / `inprogress` for steps 14–17. Skip step 18.
    - If the user answers **No** (plan only, no execution): set target status to `Plan` / `plan` for steps 14–17. Apply step 18.
13. If the assessment does not recommend `writing-plans`, create a concise implementation plan directly after the `brainstorming` gate is resolved or deemed unnecessary. Target status is `Plan` / `plan`.
14. Add or update `### Implementation Plan` in the ticket file.
15. Move the ticket entry to the correct board section based on the target status from step 12 or 13:
    - `Plan` → move to `## PLAN`
    - `In Progress` → move to `## INPROGRESS`
16. Change `Status:` and the YAML `status:` frontmatter to match the target status. Both must be updated together in the same edit.
17. Sync based on provider:
    - `local` or unset: run the project's `sync-ticket` command for `WORK-XXXX` if defined. Report any failure but do not revert.
    - `notion`: no API call for plan stage — skip.
    - `lark`: skip local sync; use Lark commands in the next step instead.
18. If optional Lark sync is enabled (or `KANBAN_PROVIDER=lark`), run `lark-move` for `WORK-XXXX` after sync, using target `plan` or `inprogress` as appropriate. Report any failure without reverting.
19. Do not implement code changes during `plan` unless the user confirmed execution already happened via `writing-plans`.

Recommend `brainstorming` when the ticket has unclear requirements, multiple possible approaches, unresolved `### Open Questions`, likely scope splitting, ambiguous data ownership, PRD tension, or decisions that should not be invented during implementation. Recommend `writing-plans` when the ticket touches multiple files, multiple layers, database changes, public SEO content, security/auth/validation behavior, external integrations, migrations, imports/exports, or has meaningful regression risk. For small copy-only, board-only, documentation-only, or single-file low-risk tickets, recommend planning without `writing-plans`.

The implementation plan should be concise but execution-ready. Include:

```md
### Implementation Plan

- Context to verify:
  - ...
- Planned changes:
  - ...
- Files likely to change:
  - ...
- Validation:
  - ...
- Risks / decisions:
  - ...
```

Scale the resulting `### Implementation Plan` to the ticket size; keep it concise for simple work and more detailed for multi-file, database, public SEO content, or regression-prone work.
