# Echo

**Turn Traditional Chinese books into Cantonese audio.**

Echo is a book-focused web application for people who want to listen to a
Traditional Chinese book in Hong Kong Cantonese. A book can begin as one PDF or
as a set of photographed pages. Both sources will eventually become the same
ordered page model before text recognition and speech generation.

## Current milestone

Milestone 6 is complete in local code. Echo can now prepare page text, split it
into ordered segments, create local mock audio by default, or create real Hong
Kong Cantonese audio when Azure Speech is configured:

- a calm landing page and `/books/new` workflow;
- PDF upload, validation, page counting, and all-page classification;
- multiple JPG/PNG page uploads with preview, ordering, rotation, and removal;
- EXIF correction followed by the user's chosen rotation;
- normalized images and original uploads in temporary UUID directories;
- one `book.json` metadata record for each locally prepared book;
- saved embedded PDF text for each qualifying page;
- rendered PNG processing copies for scanned PDF pages;
- the same ordered page fields for PDFs and page photos;
- replaceable mock and PaddleOCR page-reading providers;
- a one-page text-preview endpoint that does not alter book metadata;
- whole-book page-by-page text preparation that saves after every page;
- a `text_ready` book status that is distinct from audio-ready;
- a temporary book-detail page with progress, extracted-text review, and retry;
- safe text segmentation that keeps source page links;
- local mock WAV audio generation for free development playback;
- Azure Speech generation behind the same TTS provider boundary;
- a first `/books/<book-id>/listen` page with native audio controls;
- previous/next segment controls, playback speed, and browser-saved progress;
- safe resume behavior that skips completed pages after an interrupted local job;
- CPU-friendly PP-OCRv5 mobile models stored in an ignored local cache;
- structured errors, upload safeguards, and automated tests.

Accounts, Supabase, cloud storage, and deployment are not part of the completed
milestones.

## Core user flow

```text
Upload a PDF or page photos
→ prepare an ordered collection of pages
→ extract and save Traditional Chinese text
→ create mock or Azure Cantonese audio
→ listen to the book
```

## Technology

- Frontend: Next.js App Router, React, strict TypeScript, Tailwind CSS
- Backend: FastAPI, Pydantic, Uvicorn, typed Python
- PDF: pypdfium2 (PDFium)
- Images: Pillow
- Optional text recognition: PaddleOCR 3.5 with PaddlePaddle 3.3 CPU
- Testing: Vitest, React Testing Library, pytest, FastAPI TestClient
- Future storage and accounts: Supabase, deliberately postponed

## Prerequisites

- Node.js 20.9 or newer
- npm
- Python 3.11 or newer (milestones 1 and 2 were tested with Python 3.13.5)

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

The normal backend uses mock text reading and does not require the large OCR
runtime. To evaluate a real page locally, install the optional dependencies:

```bash
python -m pip install paddlepaddle==3.3.0 \
  -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install paddleocr==3.5.0
```

The equivalent repeatable project command is:

```bash
python -m pip install -r requirements-ocr.txt
```

Then set `USE_MOCK_OCR=false` and `OCR_ENABLED=true` in `backend/.env`. The first
real request downloads the selected models to `backend/data/models/paddlex/`.

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

Local development defaults:

```dotenv
PDF_TEXT_MIN_CHARACTERS=20
MAX_PDF_SIZE_MB=50
MAX_IMAGE_SIZE_MB=15
MAX_IMAGE_UPLOAD_COUNT=100
MAX_IMAGE_PIXELS=50000000
LOCAL_STORAGE_PATH=./data
USE_MOCK_OCR=true
OCR_ENABLED=false
OCR_TEXT_DETECTION_MODEL=PP-OCRv5_mobile_det
OCR_TEXT_RECOGNITION_MODEL=PP-OCRv5_mobile_rec
OCR_MAX_IMAGE_SIDE=2000
OCR_MODEL_CACHE_PATH=./data/models/paddlex
USE_MOCK_TTS=true
TTS_PROVIDER=azure
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
AZURE_SPEECH_VOICE=zh-HK-HiuMaanNeural
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
TTS_SEGMENT_MAX_CHARACTERS=900
```

These are development safeguards, not permanent product limits. If the backend
is started from `backend/`, uploads remain in `backend/data/<book-id>/` so they
can be inspected. Each directory contains a human-readable `book.json`. This
storage is temporary and not suitable for long-term use.

To try real Cantonese audio, create an Azure Speech resource, then set:

```dotenv
USE_MOCK_TTS=false
AZURE_SPEECH_KEY=<your key>
AZURE_SPEECH_REGION=<your resource region>
AZURE_SPEECH_VOICE=zh-HK-HiuMaanNeural
```

Restart the backend after changing these values. Leave `USE_MOCK_TTS=true` for
free local development without Azure credentials.

To try ElevenLabs instead, create a Text to Speech API key and choose a voice
ID, then set:

```dotenv
USE_MOCK_TTS=false
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=<your key>
ELEVENLABS_VOICE_ID=<your voice id>
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

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

## One-page text evaluation

After uploading a page image, preview its text with its temporary book ID:

```bash
curl --request POST \
  http://localhost:8001/api/books/<book-id>/pages/1/text-preview
```

The response includes ordered text lines, confidence values, processing time,
and the active provider. It deliberately reports `persisted: false`, making it
useful for isolated OCR evaluation.

## Whole-book text preparation

After uploading, follow the result link to `/books/<book-id>`, then choose
**Read the page text**. Echo processes unfinished pages in order, saves each page
before moving on, and shows `Page text ready` when the book reaches the internal
`text_ready` status.

The local API endpoints are:

```text
GET  /api/books/<book-id>
POST /api/books/<book-id>/process-text
POST /api/books/<book-id>/pages/<page-number>/retry-text
```

If the backend stops during preparation, restart it and use **Continue preparing
text**. Completed pages are skipped. A failed page can be retried separately.

## Listening audio

When a book shows `Page text ready`, open `/books/<book-id>/listen` and choose
**Create listening audio**. Echo splits saved page text into ordered segments
and creates WAV files using either the mock provider or Azure Speech, depending
on `USE_MOCK_TTS`.

The local API endpoints are:

```text
GET  /api/books/<book-id>/audio
POST /api/books/<book-id>/prepare-audio
GET  /api/books/<book-id>/audio/<segment-number>/file
```

Playback position and speed are saved in the browser for local development.
This is not user-account storage yet.

## Current limitations

- PDF classification is a practical character-count heuristic, not a guarantee
  that embedded text is complete or in natural reading order.
- PaddleOCR confidence is a model estimate, not proof that the wording or
  reading order is correct.
- A photographed facing page can introduce stray recognized text. Automatic
  two-page splitting and advanced cropping remain postponed.
- Real Azure Speech requires an Azure account, a key, and a region. Automated
  tests cover provider selection and missing-configuration errors, but live
  synthesis requires real credentials.
- Local book/page metadata is saved in JSON, not a database. A temporary
  book-detail API exists, but there is no book library yet.
- Successfully processed uploads are not removed automatically.
- JPG, JPEG, and PNG are supported; HEIC is postponed.
- FastAPI background tasks are local and non-durable. Restarted work can be
  resumed, but it is not a production job queue.

See [the beginner lesson](lesson.md), [architecture](docs/ARCHITECTURE.md),
[decisions](docs/DECISIONS.md), and [roadmap](docs/ROADMAP.md) for more context.
