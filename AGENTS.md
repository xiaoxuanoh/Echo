# Instructions for coding agents

Before making changes:

1. Read `README.md`.
2. Read `docs/ARCHITECTURE.md`.
3. Read `docs/ROADMAP.md`.
4. Read `docs/DECISIONS.md`.
5. Read `lesson.md`.
6. Read `tasks/SESSION_LOG.md`.
7. Inspect the existing code and repository status.
8. Make a three-step micro-plan for the current request.

While working:

- Keep work limited to the current request and milestone.
- Treat milestone 1 as complete. Do not start milestone 2 or later work without
  an explicit user request and an approved micro-plan.
- Preserve Echo's audiobook-conversion scope.
- Do not add postponed AI or learning features.
- Preserve the shared ordered-page architecture for PDFs and images.
- Keep PDF-library calls inside the dedicated PDF service.
- Keep code, documentation, errors, and explanations beginner-friendly.
- Do not commit, push, or create/switch branches unless explicitly requested.
- Preserve unrelated user changes.
- Run relevant tests and report anything not tested.
- Update `tasks/SESSION_LOG.md` after meaningful work.
- Keep the documented local port pair consistent: frontend 3001 and backend
  8001, unless the user explicitly chooses different ports.

The generated `frontend/AGENTS.md` contains additional version-specific Next.js
instructions and also applies to files inside `frontend/`.
