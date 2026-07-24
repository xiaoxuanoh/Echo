# Instructions for coding agents

Before making changes:

1. Understand and restate the user's task when the scope is not trivial.
2. Inspect only the code, tests, documentation, and repository status that are
   directly relevant to the request.
3. State assumptions clearly when they affect the implementation.
4. Make a short three-step micro-plan for meaningful implementation work.
5. Ask for confirmation before major implementation, cost, deployment,
   infrastructure, or architecture decisions unless the user has already
   authorized the change.

While working:

- Keep work limited to the current request and milestone.
- Treat milestones 1 through 6 as complete. Do not start milestone 7 or later work
  without an explicit user request and an approved micro-plan.
- Preserve Echo's current MVP scope while recognizing the long-term product as
  a multilingual document and knowledge platform.
- Do not add postponed AI or learning features.
- Preserve the shared ordered-page architecture for PDFs and images.
- Keep PDF-library calls inside the dedicated PDF service.
- Keep code, documentation, errors, and explanations beginner-friendly.
- Teach important engineering concepts briefly when they affect the user's
  understanding of the change.
- Keep dependencies restrained. Add a package only when it solves a concrete
  problem for the current approved work.
- Do not commit, push, or create/switch branches unless explicitly requested.
- Preserve unrelated user changes.
- Verify proportionally to risk using the Verification Budget below and report
  anything not tested.
- Do not automatically update project-management documents such as
  `tasks/SESSION_LOG.md`, TODO lists, milestone notes, progress logs, or
  changelogs. Complete the engineering task first and summarize changes in the
  final report. Update these documents only when the user explicitly requests
  it, approves it after task completion, or maintaining that document is the
  approved task itself.
- Keep the documented local port pair consistent: frontend 3001 and backend
  8001, unless the user explicitly chooses different ports.
- Give concise completion reports: what changed, files touched, commands run,
  tests run, known limitations, and the next practical step.

## Execution Policy

Use this workflow for meaningful work:

1. Understand.
2. Plan.
3. Implement.
4. Verify.
5. Investigate if needed.
6. Report.

Do not jump from implementation into repeated verification. If a command fails,
stalls, or behaves unexpectedly, inspect the likely cause before rerunning it.

## Repository exploration

Before implementation, inspect only the repository status and files directly
related to the approved task. Avoid repository-wide exploration unless broader
architecture understanding is actually required. Avoid repeatedly reading
unchanged files or documentation during the same task, including `AGENTS.md` and
`docs/ARCHITECTURE.md`, unless new information is needed.

## Verification Budget

Verification should stop once sufficient engineering confidence has been
obtained. Do not keep increasing confidence indefinitely. Confidence should
increase in proportion to implementation risk, not to the number of commands
executed.

- If targeted tests pass, do not automatically run broader verification unless
  the change risk justifies it.
- If lint passes and modified files are isolated, a production build may not be
  necessary.
- If a production build stalls or behaves unexpectedly, investigate before
  rerunning it.
- Do not rerun identical verification commands without a concrete reason to
  believe the outcome will change.

Before commits or milestone completion, broader verification may still be
appropriate; choose it based on risk and report anything not tested.

## Escalation Policy

If the approved task expands into a materially different task, stop and explain
the expanded scope before proceeding. Examples include architectural redesign,
database schema changes, authentication changes, infrastructure changes,
deployment changes, public API changes, or significant new dependencies. Present
the reason and wait for approval.

## Decision Recording

When a task involves a meaningful engineering decision, briefly explain the
chosen approach, one or two reasonable alternatives, and why the chosen approach
was selected. Do not generate lengthy design discussions for routine
implementation details.

## Architecture guidance

Echo's long-term domain is graph-shaped. When a task affects the domain model,
check whether it creates or changes an entity, relationship, multilingual
representation, provenance link, document structure, narration, or audio
relationship.

Examples of meaningful relationships include:

- an edition belongs to a work;
- a source document represents an edition;
- a chapter or page belongs to a document structure;
- OCR text was derived from a page;
- normalized text was derived from extracted text;
- a translation was derived from another text representation;
- a narration uses a voice to narrate a text representation;
- an audio asset was produced from a narration.

Use `docs/ARCHITECTURE.md` as the source of truth for the actual domain model.
Do not duplicate the complete conceptual graph in this file.

Distinguish Echo's conceptual domain knowledge graph from a graph database. The
conceptual graph is part of the architecture; graph-specific persistence is only
a possible future implementation choice. Use normal application structures and
PostgreSQL or Supabase initially.

Before recommending a graph database, explain:

1. the product feature that requires it;
2. the relationship queries or traversals involved;
3. why the current relational model is insufficient;
4. the expected maintenance and migration costs.

Present the options and wait for user approval before introducing graph-specific
infrastructure.

Preserve source relationships for derived content where practical. Avoid
destructively replacing the only available version when creating corrected OCR
text, normalized text, translated text, alternative OCR results, narrations,
regenerated audio, or additional language versions. Keep this proportional to
the current milestone; do not build complex versioning, event sourcing, or
provenance systems unless an approved feature requires it.

Do not read the entire architecture document for every task. For routine or
isolated work, inspect the relevant code, directly related tests, and the
specific architecture section needed. Read the conceptual domain graph and
related sections when a task affects domain entities or relationships,
multilingual representations, provenance, work or edition identity, source
documents, document structure, translations, narration, audio, or persistence
architecture. Do not repeatedly reread unchanged architecture sections during
the same task.

Propose an update to `docs/ARCHITECTURE.md` when a task materially changes a
core domain entity, important relationship, multilingual representation,
provenance rule, document structure, translation, narration, audio relationship,
provider boundary, persistence, security or privacy boundary, or overall
processing flow. Routine implementation changes that preserve the existing
design do not require an architecture update.

Keep `AGENTS.md` as the guide for AI-agent behavior and
`docs/ARCHITECTURE.md` as the source of truth for Echo's architecture. Do not
create separate knowledge-graph files, architecture summaries, decision logs,
roadmaps, session logs, or duplicate diagrams without explicit approval.

The generated `frontend/AGENTS.md` contains additional version-specific Next.js
instructions and also applies to files inside `frontend/`.

## Engineering Philosophy

Optimize for engineering quality rather than engineering activity. The objective
is not to read the most files, execute the most commands, maximize verification,
or produce unnecessarily long explanations. The objective is to understand the
problem correctly, make sound decisions, implement only the approved scope,
verify proportionally to risk, communicate clearly, and minimize unnecessary
work. Engineering confidence is more important than engineering activity.
