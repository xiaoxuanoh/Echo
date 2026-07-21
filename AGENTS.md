# Instructions for coding agents

Before making changes:

1. Read `README.md`.
2. Read `docs/ARCHITECTURE.md`.
3. Read `docs/ROADMAP.md`.
4. Read `docs/DECISIONS.md`.
5. Read `tasks/SESSION_LOG.md`.
6. Inspect the existing code and repository status.
7. Make a three-step micro-plan for the current request.

While working:

- Keep work limited to the current request and milestone.
- Preserve Echo's audiobook-conversion scope.
- Do not add postponed AI or learning features.
- Preserve the shared ordered-page architecture for PDFs and images.
- Keep PDF-library calls inside the dedicated PDF service.
- Keep code, documentation, errors, and explanations beginner-friendly.
- Do not commit, push, or create/switch branches unless explicitly requested.
- Preserve unrelated user changes.
- Run relevant tests and report anything not tested.
- Update `tasks/SESSION_LOG.md` after meaningful work.

The generated `frontend/AGENTS.md` contains additional version-specific Next.js
instructions and also applies to files inside `frontend/`.
