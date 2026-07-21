# Session log

## 2026-07-21 — Milestone 1 local foundation

### Task

Create the Echo monorepo and implement the first local PDF/image upload workflow.

### Implementation summary

- Initialized the Next.js and FastAPI applications.
- Added pypdfium2 PDF validation, extraction, rendering, and classification
  behind one service.
- Added image validation, ordering, EXIF correction, rotation, and normalization.
- Added the landing page, upload interface, local storage, structured errors,
  environment examples, documentation, and tests.
- Added `lesson.md`, a beginner-friendly explanation of the milestone's
  full-stack flow, architecture, validation, storage, types, tests, and commands.
- Configured Echo to use frontend port 3001 and backend port 8001 so it can run
  alongside another local project.

### Files changed

- Root: `.gitignore`, `AGENTS.md`, `README.md`, `lesson.md`
- Backend: configuration, error handling, API routes, schemas, PDF/image/storage
  services, environment example, pinned requirements, tests, and ignored local
  data placeholder under `backend/`
- Frontend: generated Next.js configuration and lockfile, environment example,
  landing/upload routes, upload component, API/types/validation helpers, Vitest
  setup, and tests under `frontend/`
- Documentation: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `docs/ROADMAP.md`, and this log

Development stayed on the existing `main` branch; no additional branch or pull
request was created.

### Tests run and results

- Backend pytest: 11 passed; one dependency deprecation warning. Tests cover
  valid/invalid/oversized uploads, image-count and decoded-pixel limits, order,
  rotation, EXIF correction, all PDF classifications, rendering, and health.
- Backend Ruff: passed.
- Frontend Vitest: 5 passed, including confirmed image order and rotation in the
  multipart request.
- Frontend ESLint: passed.
- Frontend production build and strict TypeScript check: passed after rerunning
  outside the restricted sandbox, where Turbopack could bind its internal port.
- Live backend `GET /health`: HTTP 200 with the expected JSON response.
- Live frontend `/` and `/books/new`: both returned HTTP 200.
- Manual browser verification: one real JPEG book-page photo was previewed,
  rotated, uploaded, normalized, and returned with a temporary book ID.
- npm production dependency audit: two moderate findings in Next.js's bundled
  PostCSS; npm's forced proposal would downgrade Next.js to 9.3.3 and was not
  applied.

### Known issues

- Real-world Traditional Chinese digital, scanned, and mixed PDFs have not yet
  been manually verified.
- The current FastAPI/Starlette TestClient emits an upstream warning that its
  `httpx` bridge is deprecated.
- Multiple real page photos, browser drag reordering, and real-world PDF uploads
  have not yet been manually verified end to end.
- Next.js 16.2.10 currently bundles a PostCSS version flagged by npm for a
  moderate XSS advisory. No non-breaking npm fix is currently offered.

### Next recommended step

Plan milestone 2: create local book/page metadata, render scanned PDF pages, and
normalize both PDF and image sources into one ordered page representation.
Continue testing representative real book files as they become available.

### Publication

- Initial milestone commit: `0df4594` (`Build Echo milestone 1 upload foundation`)
- Pushed to `origin/main` on GitHub.
- No additional branch or pull request was created.

## 2026-07-21 — Milestone 2 shared ordered pages

### Task

Create local book/page metadata, render scanned PDF pages, and normalize PDFs
and page photos into one ordered page representation.

### Implementation summary

- Added typed local `BookRecord` and `BookPageRecord` models.
- Added atomic, human-readable `book.json` metadata writing inside each UUID
  book directory.
- Saved extracted text for embedded-text PDF pages.
- Rendered PDF pages requiring future OCR into ordered normalized PNG files.
- Represented PDF and photo pages with the same IDs, order, paths, extraction
  method, rotation, status, and timestamps.
- Expanded upload responses and the result card to show every prepared page in
  ordinary user-facing language.
- Added no dependencies and did not introduce OCR, audio, Supabase, or workers.

### Files changed

- Backend: local book models, metadata service, upload routes, response schemas,
  rendered-image normalization, and upload tests.
- Frontend: upload-result types, prepared-page result UI, and component test.
- Documentation: `README.md`, `AGENTS.md`, `lesson.md`, architecture, decisions,
  roadmap, and this log.

### Tests run and results

- Backend pytest: 11 passed; the existing TestClient dependency warning remains.
- Backend Ruff: passed.
- Frontend Vitest: 5 passed.
- Frontend ESLint: passed.
- Frontend production build and strict TypeScript check: passed after rerunning
  outside the restricted sandbox so Turbopack could bind its internal port.
- Live `GET /health` on the existing backend at port 8001: passed with the
  expected development response.
- Manual browser verification: one real JPEG page was uploaded with a 270°
  rotation. The result displayed the expected ordered-page information, and
  its UUID directory contained `book.json`, the original JPEG, and normalized
  PNG with matching metadata.

Automated mixed-PDF coverage confirms embedded text is saved, scanned pages are
rendered in order, and `book.json` contains the shared page records. Automated
photo coverage confirms confirmed order, rotation, source paths, normalized
paths, and pending OCR status.

### Known issues

- Real Traditional Chinese digital, scanned, and mixed PDFs are still not
  available for manual verification.
- Multiple real photos and browser drag reordering have not been manually
  rechecked during this milestone.
- Local JSON is development persistence, not a concurrent or long-term store.
- No retrieval/library endpoint is included yet.

### Next recommended step

Plan milestone 3 around one representative Traditional Chinese image: define a
replaceable OCR service, evaluate PaddleOCR and its Python/runtime compatibility,
and measure output quality before attempting whole-book OCR.

### Publication

- Milestone 2 commit: `391a53a` (`Build Echo milestone 2 shared page foundation`)
- Pushed to `origin/main` on GitHub.
- Local `main` and `origin/main` matched after the push.
- No additional branch or pull request was created.
