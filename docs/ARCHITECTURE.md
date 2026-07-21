# Echo architecture

## System overview

Echo is a monorepo with two independently started applications:

```text
Browser (Next.js)
  → multipart upload
FastAPI
  → validation and source-specific preparation
Temporary local storage (milestone 1)
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

Milestone 1 stops before creating persistent `book_pages` records. It already
preserves the order and processing metadata needed for that model in milestone
2.

## PDF processing flow

1. Stream the upload to a size-limited UUID directory.
2. Confirm the PDF signature and ask PDFium to open the document.
3. Reject unreadable, password-protected, or zero-page documents.
4. Extract text from every page through `PdfProcessingService`.
5. Count non-whitespace characters per page.
6. Mark pages with at least `PDF_TEXT_MIN_CHARACTERS` as `embedded_text`; mark
   the rest as `requires_ocr`.
7. Return `text`, `scanned`, or `mixed` from the full set of page results.

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

## Planned OCR flow

In milestones 3 and 4, only pages marked `requires_ocr` will go through the OCR
service. Uploaded image pages and rendered scanned-PDF pages will share that
service. Results will be stored separately per page, and OCR output will never
be assumed perfect.

## Planned Cantonese speech flow

In milestones 5 and 6, page text will be divided into safe ordered segments.
Each audio record will retain its source text and source page. A mock provider
will work locally before Azure Speech is enabled with a configurable `zh-HK`
voice.

## Storage model

Milestone 1 uses:

```text
backend/data/<book-id>/
├── source.pdf                 # PDF flow
└── originals/ + pages/       # image flow
```

The complete model will use `books`, `book_pages`, `audio_segments`, and
`reading_progress`. Supabase Postgres and Storage are postponed until milestone
8. User ownership and Row Level Security will be designed with authentication.

## Planned deployment

- Next.js frontend: suitable for Vercel
- Containerized FastAPI backend: suitable for Railway, Render, or similar
- Database and object storage: Supabase in a later milestone
- Long-running processing: a worker queue only when measurements demonstrate a
  need

Local development must remain functional without cloud or paid services.
