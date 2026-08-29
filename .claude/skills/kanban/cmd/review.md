# Review Ticket

For `/kanban review WORK-XXXX`:

1. Read `obsidian/kanban/context/kanban-flow.md`.
2. Read `prd.md` when the ticket affects product scope, public pages, admin-managed website content, SEO, structured data, content quality, or user-facing behavior.
3. Use the `scrutinize` skill when the plan, diff, or code change has regression risk, cross-layer impact, important behavior changes, or the user asked for review/audit/sanity-check/second opinion.
4. Use the `fullstack-guardian` skill when the ticket has full-stack, security, auth, validation, form submission, database write, upload, CRUD, route contract, data-model relationship, authorization rule, request middleware, admin panel resource/action, or high regression impact.
5. If the ticket is low-risk and does not need `scrutinize` or `fullstack-guardian`, run the lightweight review described in `obsidian/kanban/context/kanban-flow.md` and record why those gates were skipped.
6. Review against the acceptance criteria, PRD alignment when applicable, and gates in `obsidian/kanban/context/kanban-flow.md`.
7. Report `PASS`, `NEEDS FIX`, or `BLOCKED`.
8. If fixes are required, implement them before moving the ticket forward. Use `debug-mantra` for new bug/regression root-cause work and `systematic-debugging` for unclear test/build/runtime failures.
