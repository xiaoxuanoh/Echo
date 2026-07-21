# Echo milestone 1 lesson

This lesson explains what we built, why it is structured this way, and what you
can learn from it as a beginner.

## 1. What “full stack” means here

Echo has two applications that work together:

```text
Next.js frontend → HTTP request → FastAPI backend → local files
```

The **frontend** is what the user sees. It displays buttons, previews page
photos, remembers their order, and shows results.

The **backend** receives uploads and makes the final safety decisions. It checks
the real file content, inspects PDFs, normalizes images, and stores temporary
files.

This separation matters because browser checks can be bypassed. Frontend
validation makes the experience friendlier, while backend validation protects
the application.

## 2. Why Echo is a monorepo

A monorepo keeps related applications in one repository:

```text
frontend/   # Next.js and TypeScript
backend/    # FastAPI and Python
docs/       # architecture, roadmap, and decisions
tasks/      # a record of completed work
```

The frontend and backend remain clearly separated, but their API contract and
documentation can evolve together.

## 3. How a PDF upload works

When the user submits a PDF:

1. The browser checks its apparent type and size.
2. FastAPI streams it to a generated UUID directory while enforcing the size
   limit.
3. `PdfProcessingService` checks the PDF content and opens it with pypdfium2.
4. The service examines every page, not only the first page.
5. A page with at least 20 non-whitespace extracted characters is marked
   `embedded_text`; otherwise it is marked `requires_ocr`.
6. The complete PDF is classified as `text`, `scanned`, or `mixed`.
7. The backend returns a typed JSON result for the frontend to display.

The 20-character threshold is configurable with:

```dotenv
PDF_TEXT_MIN_CHARACTERS=20
```

This rule detects whether a useful-looking text layer probably exists. It does
not guarantee that the text is correct or in natural reading order.

## 4. Why PDF code has its own service

Routes should describe HTTP behavior, such as receiving a file and returning a
response. They should not contain lots of library-specific processing code.

Echo keeps pypdfium2 calls inside `PdfProcessingService`, which provides:

- `validate_pdf()`
- `count_pages()`
- `extract_page_text()`
- `render_page()`
- `classify_pdf()`

If Echo later needs a different PDF library or a fallback extractor, most of the
application will not need to change.

This is a useful abstraction because PDF handling is a substantial,
replaceable responsibility. It does not mean every small helper needs an
interface or class.

## 5. How page-photo uploads work

The frontend stores each selected image with:

- a temporary ID;
- the original browser `File`;
- a preview URL;
- a rotation value.

The user can reorder, rotate, remove, or add pages. When submitted, the files are
placed in `FormData` in the confirmed order. A matching rotation array is sent
with them.

The backend then:

1. Enforces the number of files and size of every file.
2. Opens each file with Pillow to verify that it is really JPEG or PNG content.
3. Checks the decoded pixel count.
4. Saves the original using a generated safe filename.
5. Corrects camera EXIF orientation.
6. Applies the user's rotation.
7. Saves an ordered normalized PNG copy.

EXIF correction comes first because a phone photo may already contain hidden
orientation instructions. User rotation should be applied to the correctly
oriented image the user saw.

## 6. Why filenames and directories are generated

Original filenames are useful for display but unsafe as storage paths. They may
contain spaces, unusual characters, duplicate names, or path-like content.

Echo preserves the original name as metadata while writing files under a UUID:

```text
backend/data/<book-id>/
```

Internal filenames such as `page-0001.png` are predictable and safe. The UUID
prevents different uploads from overwriting each other.

Milestone 1 deliberately keeps successful uploads so they can be inspected
during development. This is temporary storage, not a permanent library.

## 7. Environment variables

Environment variables let behavior change without editing source code. For
example:

```dotenv
MAX_PDF_SIZE_MB=50
MAX_IMAGE_SIZE_MB=15
MAX_IMAGE_UPLOAD_COUNT=100
MAX_IMAGE_PIXELS=50000000
```

The repository contains `.env.example` files with safe placeholders. Actual
`.env` files are ignored by Git so secrets will not be committed accidentally.

Supabase and Azure variables are only placeholders for future milestones. No
cloud account is required now.

Echo currently uses a project-specific local port pair so it can run beside
another web project:

```text
Frontend: http://localhost:3001
Backend:  http://localhost:8001
```

The matching values are:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001

# backend/.env
FRONTEND_ORIGIN=http://localhost:3001
```

`NEXT_PUBLIC_API_BASE_URL` tells the browser where to send an upload.
`FRONTEND_ORIGIN` tells FastAPI which browser origin may call it. If either value
is stale, the browser can show `Failed to fetch` even when both servers appear
to be running. Restart both development servers after changing these files.

## 8. Why types and schemas matter

TypeScript types describe the result the frontend expects. Pydantic models
describe what the backend returns.

For example, both sides agree that a PDF result includes:

- a temporary book ID;
- source type;
- filename;
- page count;
- document classification;
- page-level results;
- processing status.

Types catch many mistakes while developing, but they do not replace runtime
validation. Data arriving over HTTP must still be checked by the backend.

## 9. What the tests teach us

The test suite uses generated PDFs and images so it can run without private book
files. It checks:

- health endpoint behavior;
- text, scanned, and mixed PDF classification;
- embedded-text extraction and page rendering;
- invalid and oversized uploads;
- image count and decoded-pixel safeguards;
- EXIF correction and user rotation;
- confirmed image order sent by the frontend;
- frontend file validation.

A passing synthetic test proves a defined behavior is repeatable. It does not
prove that every real Traditional Chinese book will extract cleanly. Real sample
testing is still essential before adding OCR.

## 10. How to run Echo

Start the backend in one terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Start the frontend in another terminal:

```bash
cd frontend
npm run dev -- --port 3001
```

Then open:

```text
http://localhost:3001/books/new
```

## 11. Useful debugging sequence

If an upload fails, check the system one layer at a time:

1. Visit `http://localhost:8001/health` to confirm the backend is running.
2. Check the browser error message.
3. Look at the FastAPI terminal output.
4. Confirm `NEXT_PUBLIC_API_BASE_URL` points to the backend.
5. Check the configured file-size and image-count limits.
6. Inspect `backend/data/<book-id>/` after a successful upload.
7. Run the relevant automated tests before changing code.

This approach narrows the problem instead of guessing across the entire stack.

During milestone 1 verification, a real JPEG page initially showed `Failed to
fetch` because the frontend and backend ports/origins did not match. After both
environment files were aligned and the servers restarted, the same page upload
completed successfully. This is a useful example of configuration debugging:
the image-processing code was working, but the request could not cross the
frontend/backend boundary.

## 12. What comes next

Milestone 2 should create the shared ordered page model and render scanned PDF
pages into normalized images. It should not add OCR, audio, authentication, or
cloud storage yet.

The central idea to preserve is:

```text
PDF pages or photo pages
→ one ordered page representation
→ text
→ audio segments
→ listening
```

Building one small vertical slice at a time keeps Echo understandable and makes
each new capability easier to test.
