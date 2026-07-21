# Echo

**Turn Traditional Chinese books into Cantonese audio.**

Echo is a book-focused web application for people who want to listen to a
Traditional Chinese book in Hong Kong Cantonese. A book can begin as one PDF or
as a set of photographed pages. Both sources will eventually become the same
ordered page model before text recognition and speech generation.

## Current milestone

Milestone 1 is complete and provides a local upload foundation:

- a calm landing page and `/books/new` workflow;
- PDF upload, validation, page counting, and all-page classification;
- multiple JPG/PNG page uploads with preview, ordering, rotation, and removal;
- EXIF correction followed by the user's chosen rotation;
- normalized images and original uploads in temporary UUID directories;
- structured errors, upload safeguards, and automated tests.

Real text recognition, Cantonese audio, accounts, Supabase, and deployment are
not part of this milestone.

The next planned step is milestone 2: create the shared ordered-page model and
render scanned PDF pages into the same normalized representation used by page
photos. Milestone 2 has not started yet.

## Core user flow

```text
Upload a PDF or page photos
→ prepare an ordered collection of pages
→ extract Traditional Chinese text (future milestone)
→ create Cantonese audio (future milestone)
→ listen to the book (future milestone)
```

## Technology

- Frontend: Next.js App Router, React, strict TypeScript, Tailwind CSS
- Backend: FastAPI, Pydantic, Uvicorn, typed Python
- PDF: pypdfium2 (PDFium)
- Images: Pillow
- Testing: Vitest, React Testing Library, pytest, FastAPI TestClient
- Future storage and accounts: Supabase, deliberately postponed

## Prerequisites

- Node.js 20.9 or newer
- npm
- Python 3.11 or newer (milestone 1 was tested with Python 3.13.5)

## Backend setup

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

The API is available at `http://localhost:8001`; its interactive documentation
is at `http://localhost:8001/docs`.

## Frontend setup

In a second terminal, from the repository root:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev -- --port 3001
```

Open `http://localhost:3001/books/new`.

Echo uses ports 3001 and 8001 so it can run beside another common local project
using ports 3000 and 8000. The frontend and backend environment values must
match these addresses, and both servers must be restarted after changing them.

## Environment variables

Copy the provided example files rather than editing them with secrets:

- `frontend/.env.example` contains the backend URL. Supabase values are empty
  placeholders for a later milestone.
- `backend/.env.example` contains local paths, classification settings, future
  provider placeholders, and upload safeguards.

Milestone 1 defaults:

```dotenv
PDF_TEXT_MIN_CHARACTERS=20
MAX_PDF_SIZE_MB=50
MAX_IMAGE_SIZE_MB=15
MAX_IMAGE_UPLOAD_COUNT=100
MAX_IMAGE_PIXELS=50000000
LOCAL_STORAGE_PATH=./data
```

These are development safeguards, not permanent product limits. If the backend
is started from `backend/`, uploads remain in `backend/data/<book-id>/` so they
can be inspected. This storage is temporary and not suitable for long-term use.

## Testing commands

Frontend:

```bash
cd frontend
npm run test:run
npm run lint
npm run build
```

Backend:

```bash
cd backend
source .venv/bin/activate
python -m pytest
ruff check app tests
```

Health check while the backend is running:

```bash
curl --fail http://localhost:8001/health
```

## Current limitations

- PDF classification is a practical character-count heuristic, not a guarantee
  that embedded text is complete or in natural reading order.
- No OCR is run. Pages without enough embedded text are only marked as needing
  text recognition later.
- No audio is generated.
- Local upload metadata is returned to the browser but is not stored in a
  database.
- Successfully processed uploads are not removed automatically.
- JPG, JPEG, and PNG are supported; HEIC is postponed.
- A real background worker is postponed until processing volume requires one.

See [the beginner lesson](lesson.md), [architecture](docs/ARCHITECTURE.md),
[decisions](docs/DECISIONS.md), and [roadmap](docs/ROADMAP.md) for more context.
