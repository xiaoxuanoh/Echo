# Echo architecture

## System overview

Echo is a monorepo with two independently started applications:

```text
Browser (Next.js)
  → multipart upload
FastAPI
  → validation and source-specific preparation
Temporary local storage (milestones 1–3)
```

The frontend explains the workflow, gathers a confirmed page order, and shows
results. The backend is authoritative for validation and file preparation.

## Frontend responsibilities

- Present ordinary book language rather than processing jargon.
- Provide separate PDF and page-photo choices.
- Check obvious file type, size, and count problems before upload.
- Preview, reorder, rotate, remove, and add page images.
- Send images in confirmed order with one rotation value per image.
- Display structured backend results and understandable errors.

Interactive upload logic is kept in a focused Client Component. Static route
content remains in Server Components.

## Backend responsibilities

- Enforce upload size, count, rotation, decoded format, and pixel limits.
- Store uploads under generated UUID directories and generated filenames.
- Inspect every PDF page rather than inferring the whole document from page one.
- Correct EXIF orientation before applying the confirmed user rotation.
- Return stable typed responses and structured errors.
- Save one portable local book record with a shared ordered page list.

Routes coordinate requests; PDF, image, validation, and storage logic live in
independently testable services.

## Shared ordered-page architecture

The eventual normalization boundary is:

```text
PDF                         Page photographs
 ├─ embedded text page       ├─ confirmed order
 └─ rendered scanned page    └─ normalized image
            \                /
             ordered book pages
                     ↓
          text → segments → audio
```

Milestone 2 creates local `BookRecord` and `BookPageRecord` models. PDF and
photo uploads now produce the same ordered page fields: page ID and number,
source paths, normalized path, extraction method, extracted text, rotation,
status, and timestamps. The records are stored together in `book.json` until a
database is introduced.

## PDF processing flow

1. Stream the upload to a size-limited UUID directory.
2. Confirm the PDF signature and ask PDFium to open the document.
3. Reject unreadable, password-protected, or zero-page documents.
4. Extract text from every page through `PdfProcessingService`.
5. Count non-whitespace characters per page.
6. Save text for pages with at least `PDF_TEXT_MIN_CHARACTERS` and mark them
   `embedded_text`.
7. Render every `requires_ocr` page to an ordered normalized PNG.
8. Save both page kinds in one ordered page list and return `text`, `scanned`,
   or `mixed` from the full set.

`PdfProcessingService` owns `validate_pdf()`, `count_pages()`,
`extract_page_text()`, `render_page()`, and `classify_pdf()`. No PDF-library calls
belong in routes.

## Image processing flow

1. Receive files in the user's confirmed order.
2. Enforce per-file size and total-count limits.
3. Decode each file with Pillow and accept only actual JPEG or PNG content.
4. Reject images over the configured decoded pixel count.
5. Save the original using a generated filename.
6. Correct EXIF orientation.
7. Apply the confirmed clockwise rotation: 0°, 90°, 180°, or 270°.
8. Save an ordered normalized PNG processing copy.

Automatic two-page splitting, dewarping, and background removal are excluded.

## OCR flow

Milestone 3 adds an `OcrProvider` boundary with mock and PaddleOCR
implementations. The one-page preview endpoint resolves a normalized page from
the shared page record, calls one provider, and returns text lines, confidence
estimates, and processing time. It does not update `book.json`.

The real provider lazily imports PaddleOCR so the API can still start in mock
mode without the optional runtime. It uses the PP-OCRv5 mobile detector and
multilingual recognizer on CPU, limits the longest inference side to 2,000
pixels, and stores model files under the ignored local data directory. The
mobile recognizer supports Traditional Chinese while using substantially less
memory than the server models.

Milestone 4 will send every `requires_ocr` page through this same boundary,
store results separately per page, and manage page statuses and retries. OCR
output will never be assumed perfect.

## Planned Cantonese speech flow

In milestones 5 and 6, page text will be divided into safe ordered segments.
Each audio record will retain its source text and source page. A mock provider
will work locally before Azure Speech is enabled with a configurable `zh-HK`
voice.

## Storage model

Milestone 2 uses:

```text
backend/data/<book-id>/
├── book.json                  # book plus ordered page metadata
├── source.pdf                 # PDF flow
├── originals/                 # original photo uploads, image flow
└── pages/                     # normalized photos or rendered PDF pages
```

Embedded-text PDF pages can have no processing image. Photo pages and scanned
PDF pages have a normalized PNG path and are marked as waiting for future OCR.
All stored paths are relative to the UUID book directory.

The complete model will add `audio_segments` and `reading_progress`, then move
the local book/page records to Supabase in milestone 8. User ownership and Row
Level Security will be designed with authentication.

## Planned deployment

- Next.js frontend: suitable for Vercel
- Containerized FastAPI backend: suitable for Railway, Render, or similar
- Database and object storage: Supabase in a later milestone
- Long-running processing: a worker queue only when measurements demonstrate a
  need

Local development must remain functional without cloud or paid services.
