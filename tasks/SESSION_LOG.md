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

## 2026-07-22 — Milestone 3 first Traditional Chinese page

### Task

Add a replaceable OCR service and evaluate exactly one representative
Traditional Chinese page without starting whole-book processing.

### Implementation summary

- Added mock and PaddleOCR providers behind one typed `OcrProvider` boundary.
- Added a one-page `text-preview` API that reads normalized shared-page images
  without changing `book.json`.
- Added confidence, timing, provider, and non-persistence fields to the result.
- Kept real OCR optional and disabled by default.
- Installed and verified PaddlePaddle 3.3.0 and PaddleOCR 3.5.0 locally.
- Stored downloaded model files in the ignored project-local data cache.
- Switched from server to mobile PP-OCRv5 models after the server models were
  terminated with exit 137 on the full-resolution photo.
- Added no whole-book OCR, audio, frontend OCR controls, Supabase, or workers.

### Files changed

- Backend: OCR configuration, optional requirements, OCR service, page-preview
  response schemas and route, metadata loading, and OCR tests.
- Documentation: `README.md`, `AGENTS.md`, `lesson.md`, architecture, decisions,
  roadmap, and this log.

### Real-page evaluation

- Input: the existing normalized 3024-by-4032 Traditional Chinese page photo.
- Mobile models downloaded successfully and were reused from cache afterward.
- Cached run: 35 non-empty lines, average reported confidence 0.9407, about
  8.2 seconds on Apple Silicon CPU.
- Most text on the intended right-hand page was readable.
- Known errors included incorrect characters and punctuation plus stray text
  from the partially visible facing page.
- No preprocessing was added because automatic facing-page separation is out of
  scope and the current image provides a useful baseline.

### Tests run and results

- Backend pytest: 15 passed, including four one-page OCR tests; the existing
  FastAPI/Starlette TestClient deprecation warning remains.
- Backend Ruff: passed.
- PaddlePaddle runtime check: passed on one Apple Silicon CPU.
- PaddleOCR imports and reports version 3.5.0.
- Optional OCR requirements dry-run: passed with all pinned packages satisfied.
- Cached real PaddleOCR evaluation: passed with no repeat download.
- Live `GET /health` on port 8001: HTTP 200 with the expected response.
- Live one-page preview on the existing temporary book: HTTP 200 in mock mode,
  with `persisted: false` and the expected Traditional Chinese mock text.
- Frontend Vitest: 5 passed.
- Frontend ESLint: passed.
- Frontend production build and strict TypeScript check: passed outside the
  restricted sandbox after the expected internal-port denial inside it.

### Known issues

- Confidence values do not prove textual correctness or reading order.
- The synchronous preview request can take several seconds after models are
  cached and considerably longer on the first download.
- The unused server-model files from the failed baseline remain in ignored
  local cache; they are not committed.
- Whole-book persistence, statuses, and retry handling remain milestone 4.

### Next recommended step

Plan milestone 4 around orchestration that processes every OCR-required page,
persists each result safely, records page statuses, and supports retrying failed
pages without redoing completed work.

### Publication

- Milestone 3 commit: `80353d1` (`Build Echo milestone 3 OCR preview`)
- Pushed to `origin/main` on GitHub.
- No additional branch or pull request was created.

## 2026-07-22 — Milestone 4 whole-book text preparation

### Task

Process all pages in a temporary book, save text and page-level status, support
failed-page retry and interrupted-job resume, and use `text_ready` for text
completion.

### Implementation summary

- Added a `BookTextProcessingService` that works through unfinished pages in
  order and saves `book.json` after every state transition.
- Preserved embedded PDF text and sent only OCR pages through the configured
  provider.
- Added `text_ready` as a distinct state before audio-ready `ready`.
- Added book-detail, whole-book processing, and failed-page retry endpoints.
- Added page-level friendly error persistence and retry behavior.
- Added FastAPI background tasks plus a process-local duplicate-job registry.
- Added resume behavior that skips completed pages and detects stale running
  status after a development server restart.
- Added `/books/[id]` with progress, extracted-text review, and retry controls.
- Kept Supabase, audio, a production worker queue, and new dependencies out of
  this milestone.

### Files changed

- Backend: book/page models, response schemas, application state, OCR provider
  selection, book routes, the new orchestration service, and processing tests.
- Frontend: book API/types, upload-result continuation link, dynamic book route,
  processing/status component, and component tests.
- Documentation: `README.md`, `AGENTS.md`, `lesson.md`, architecture, decisions,
  roadmap, and this log.

### Tests run and results

- Backend pytest: 21 passed; the existing FastAPI/Starlette TestClient
  deprecation warning remains.
- Backend Ruff check: passed.
- Frontend Vitest: 8 passed.
- Frontend ESLint: passed.
- Frontend production build and strict TypeScript check: passed outside the
  restricted sandbox after the expected Turbopack internal-port denial inside
  it.
- Live `GET /health` on port 8001: HTTP 200 with the expected development
  response.
- Live `GET /api/books/<book-id>`: three existing temporary image books returned
  their ordered page details and `processing_active: false` without mutation.
- Live frontend `/books/<book-id>` route on port 3001: HTTP 200.
- Automated coverage includes ordered multi-page processing, mixed PDFs,
  embedded-text preservation, OCR-disabled digital PDFs, saved failures,
  one-page retry, completed-page resume behavior, API status responses, UI
  completion, UI retry, and interrupted-job continuation.

### Known issues

- Milestone 4 whole-book orchestration was verified with synthetic files and
  mock OCR. The real PaddleOCR provider was verified on one page in milestone
  3, but a representative multi-page real Traditional Chinese book was not
  available for an end-to-end manual run.
- FastAPI `BackgroundTasks` and the in-memory registry are not a durable worker
  queue. A backend restart stops active work, but saved pages can be resumed.
- The registry prevents duplicate jobs only inside one backend process.
- Local JSON can be inspected and resumed but is not suitable for concurrent or
  long-term production persistence.
- OCR errors and reading-order limitations from milestone 3 still apply.

### Next recommended step

Plan milestone 5: segment the saved text safely, create local mock audio, and
build the first basic listening page without adding Azure Speech yet.

### Publication

- Milestone 4 commit: `74e62a6` (`Build Echo milestone 4 text preparation`)
- Pushed to `origin/main` on GitHub.
- No additional branch or pull request was created.

## 2026-07-22 — Milestone 5 segments and mock listening

### Task

Split prepared page text into ordered audio-sized segments, create local mock
audio, and add the first listening page without Azure Speech, Supabase, or new
infrastructure.

### Implementation summary

- Added persisted local audio segment records to `book.json`.
- Added a text segmentation service with configurable maximum segment length.
- Added a mock TTS provider that creates local WAV files with Python's standard
  library.
- Added an audio processing service that creates ordered mock audio and marks
  the book `ready` when every segment has a playable file.
- Added audio detail, prepare-audio, and local audio-file endpoints.
- Added `/books/[id]/listen` with a native audio player, previous/next segment
  controls, playback speed, source-text review, and browser-local progress.
- Linked text-ready and audio-ready books from the book detail page to the
  listening page.
- Kept Azure Speech, Supabase, authentication, durable workers, translation,
  graph infrastructure, and new dependencies out of this milestone.

### Files changed

- Backend: settings, book models, response schemas, book routes, text
  segmentation service, mock TTS provider, audio orchestration service, and
  audio processing tests.
- Frontend: book/audio API helpers, shared types, book-detail listening links,
  listening route, audio player component, and component tests.
- Documentation: `README.md`, `AGENTS.md`, `lesson.md`, architecture,
  decisions, roadmap, environment example, and this log.

### Tests run and results

- Backend pytest: 25 passed; the existing FastAPI/Starlette TestClient
  deprecation warning remains.
- Backend Ruff check: passed.
- Frontend Vitest: 11 passed.
- Frontend ESLint: passed.
- Frontend production build and strict TypeScript check: passed outside the
  restricted sandbox after the expected Turbopack internal-port denial inside
  it.
- `git diff --check`: passed.

### Not manually verified

- Live `GET /health` on port 8001 was not verified in this turn because no
  backend response was available from the shell when checked.
- A real uploaded book was not manually played through the browser in this turn.
  The mock audio endpoint was verified by automated tests returning a WAV file
  beginning with the expected `RIFF` header.

### Known issues

- Mock audio is a generated placeholder tone, not real Cantonese narration.
- Browser progress is saved in localStorage only. It is not account-backed and
  will not sync across browsers.
- FastAPI `BackgroundTasks` and the in-memory registry remain local and
  non-durable.
- Local JSON and WAV files remain development storage, not production
  persistence.

### Next recommended step

Review Milestone 5 locally by preparing a text-ready book, opening
`/books/<book-id>/listen`, creating mock audio, and playing the generated
segments. If accepted, commit and push Milestone 5 before planning Milestone 6
Azure Speech.

## 2026-07-22 — Milestone 6 Azure Cantonese audio

### Task

Add real Hong Kong Cantonese speech generation while keeping mock TTS available
for local development.

### Implementation summary

- Added Azure Speech SDK as a backend dependency.
- Added Azure Speech settings for key, region, and configurable voice.
- Added a typed TTS provider boundary with mock and Azure implementations.
- Kept mock TTS as the default when `USE_MOCK_TTS=true`.
- Updated audio preparation to select the provider from settings.
- Kept generated audio as WAV files so the existing audio endpoint and frontend
  player continue to work.
- Added clear backend errors when real speech is selected without required Azure
  key or region.
- Kept Supabase, authentication, cloud storage, deployment, translation, graph
  infrastructure, and synchronized text highlighting out of this milestone.

### Files changed

- Backend: settings, TTS provider, audio orchestration, book routes, dependency
  list, environment example, and audio processing tests.
- Documentation: README, architecture, decisions, roadmap, lesson, and this log.

### Tests run and results

- Focused backend audio tests: 7 passed; the existing FastAPI/Starlette
  TestClient deprecation warning remains.
- Backend Ruff check: passed.
- Azure Speech SDK import check: passed with version 1.50.0.

### Not manually verified

- Live Azure synthesis was not tested because no real Azure Speech credentials
  were provided during this turn.
- Frontend tests/build were not rerun because Milestone 6 did not change
  frontend code.

### Known issues

- Real speech generation depends on Azure account credentials and network
  access.
- Invalid Azure credentials or provider-side failures are still handled as
  segment-generation failures in the local background task flow.
- Local JSON and WAV files remain development storage, not production
  persistence.

### Next recommended step

Configure a real Azure Speech key and region in `backend/.env`, set
`USE_MOCK_TTS=false`, restart the backend, and test one short text-ready book.
If accepted, commit and push Milestone 6 before planning Milestone 7.

## 2026-07-23 — ElevenLabs local TTS test provider

### Task

Add a narrow backend-only ElevenLabs provider so Milestone 6's real-audio path
can be tested locally while Azure account authentication is blocked.

### Implementation summary

- Added `TTS_PROVIDER=elevenlabs` configuration while preserving mock TTS as the
  default and Azure as the existing real provider.
- Added an ElevenLabs TTS provider using the Python standard library HTTP
  client, so no new dependency was added.
- Saved ElevenLabs output as MP3 segments and returned the matching media type
  from the existing audio-file endpoint.
- Updated local environment documentation for ElevenLabs API key, voice ID,
  model ID, and output format.

## 2026-07-24 — Handoff note: pending CJK text normalization fix

### Current state

- Edge TTS has replaced the local ElevenLabs test provider for real speech
  testing.
- Generated audio now plays real Mandarin speech instead of the mock tone.
- Text normalization has improved PDF visual line-break handling, but one
  remaining artifact persists in extracted Chinese text:
  `⽅⾯擁有 ⻑期經驗`.

### Pending fix

- Extend `TextSegmentationService._is_cjk()` in
  `backend/app/services/text_segmentation.py` so it treats CJK radical and
  Kangxi radical code-point ranges as CJK:
  - `U+2E80-U+2EFF`
  - `U+2F00-U+2FDF`
- Keep the existing CJK ranges:
  - `U+3400-U+4DBF`
  - `U+4E00-U+9FFF`
  - `U+F900-U+FAFF`
- Add a focused test for:
  `⽅⾯擁有 ⻑期經驗` -> `⽅⾯擁有⻑期經驗`.

### Important context

- Do not automatically update project-management docs except when explicitly
  requested.
- `tasks/SESSION_LOG.md` already had uncommitted changes before this handoff
  note.
