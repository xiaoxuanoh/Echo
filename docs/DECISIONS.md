# Technical decisions

## One ordered page model for PDFs and images

**Decision:** Normalize both inputs into ordered book pages.

**Reason:** OCR, text storage, segmentation, audio, and playback should not need
separate PDF and photo implementations. This also supports mixed PDFs, where
some pages have embedded text and others need OCR.

## pypdfium2 for PDF handling

**Decision:** Use pypdfium2 alone in milestone 1, isolated behind
`PdfProcessingService`.

**Reason:** PDFium can validate/open documents, count pages, extract a page's
embedded text, and render pages. pypdfium2 is available under Apache-2.0 or
BSD-3-Clause, while its PDFium binary includes additional permissive third-party
notices. This avoids PyMuPDF's AGPL/commercial-license decision for the
prototype.

For full-page Unicode text, the service uses `get_text_bounded()`. PDF text does
not contain a guaranteed semantic reading order. Unusual font encodings,
positioned glyphs, or damaged text layers can therefore produce missing,
misordered, or unusable text. The milestone's 20-character rule only detects a
plausible text layer; it does not prove readability.

We are not adding `pypdf` now because it would introduce a second parser without
guaranteeing better results. If representative Traditional Chinese PDFs reveal
a repeatable PDFium-specific extraction failure, `pypdf` can be evaluated as a
fallback inside the same service boundary without changing API routes.

## Configurable PDF classification

**Decision:** A page with at least `PDF_TEXT_MIN_CHARACTERS` non-whitespace
characters is `embedded_text`; otherwise it is `requires_ocr`. The default is
20.

All embedded-text pages produce a `text` PDF, all OCR-required pages produce a
`scanned` PDF, and a combination produces `mixed`. Every page is inspected.

## JSON for milestone-two local metadata

**Decision:** Save one `book.json` inside each UUID book directory. It contains
the book record and its ordered page records. File paths inside it are relative
to that directory.

**Reason:** JSON is inspectable while learning, requires no database service,
and is sufficient for the local prototype. Writing through a temporary file
reduces the chance of leaving half-written metadata. This is intentionally not
a long-term concurrent database and will be replaced by Supabase in milestone
8.

Embedded-text PDF pages store their text directly and need no rendered image.
PDF pages that require OCR are rendered to PNG, while uploaded photos retain
both their generated original path and normalized PNG path. Both sources use
the same `BookPageRecord` shape.

## Pillow now, OpenCV later

**Decision:** Use Pillow for decoding, EXIF orientation, right-angle rotation,
and normalized PNG output.

**Reason:** These milestone operations do not require OpenCV. OpenCV can be
introduced later only if OCR tests show that contrast, thresholding, denoising,
or perspective correction materially improves results.

## PaddleOCR is planned, not installed

**Decision:** Introduce PaddleOCR only when milestone 3 tests one Traditional
Chinese page.

**Reason:** Delaying the large OCR runtime keeps the foundation quick to install
and allows the OCR provider to be mocked and evaluated with real pages first.

## Azure Speech is planned behind a provider

**Decision:** Later provide both mock speech and Azure Speech implementations,
with a configurable Hong Kong Cantonese voice.

**Reason:** Local development must work without paid credentials, and speech
vendors should not leak into page or playback code.

## Supabase is postponed

**Decision:** Milestones 1 and 2 have no Supabase runtime package, schema, CLI
setup, or cloud dependency.

**Reason:** Temporary local storage is enough to prove both upload paths. Auth,
Postgres, Storage, and ownership-based Row Level Security will arrive together
in milestone 8, after the core processing model is stable.

## No advanced AI or learning features

**Decision:** Exclude LLM correction, summaries, chat, translation, vocabulary,
flashcards, and synchronized highlighting from the MVP.

**Reason:** Echo's first job is reliable audiobook conversion and listening.
Extra product directions would make that core harder to test and understand.
