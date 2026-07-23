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

## Optional PaddleOCR behind a provider

**Decision:** Keep the base backend lightweight and place PaddlePaddle 3.3 and
PaddleOCR 3.5 in `requirements-ocr.txt`. Use an `OcrProvider` boundary with mock
and PaddleOCR implementations. Real OCR remains disabled by default.

**Reason:** Local development and automated tests should not require model
downloads. Lazy imports also let FastAPI start when only the base requirements
are installed.

The first real Apple Silicon test showed that the default PP-OCRv5 server
detector and recognizer exceeded the practical memory available for a
3024-by-4032 page photo and were terminated with exit 137. Echo therefore uses
the configurable `PP-OCRv5_mobile_det` and `PP-OCRv5_mobile_rec` models with a
2,000-pixel longest-side inference limit. The mobile recognizer supports
Traditional Chinese, English, Simplified Chinese, and Japanese.

The successful cached run found 35 lines at an average reported confidence of
about 0.941 and took about 8.2 seconds on CPU after model download. Most main
page text was readable. It also recognized stray text from the visible facing
page and made several character and punctuation errors. Confidence is therefore
diagnostic information, not a correctness guarantee. Automatic page splitting
is still excluded from the MVP.

**Decision:** Milestone 3 returns a one-page preview with `persisted: false`.

**Reason:** This proves the provider and measures real quality without quietly
implementing milestone 4's whole-book persistence and retry behavior.

## `text_ready` is separate from audio-ready

**Decision:** Use `text_ready` when all book pages have saved text. Keep `ready`
for the later point when a book has playable audio.

**Reason:** A book with extracted text is not yet ready for Echo's main listening
experience. Separate names make backend state, frontend messages, and later
audio orchestration much less ambiguous.

## Save whole-book progress page by page

**Decision:** The book processing service saves metadata before and after each
page, skips completed pages on resume, and lets the user retry one failed page.

**Reason:** OCR can take several seconds per page. Saving only at the end would
lose useful work if the local backend stops, while rerunning completed pages
would waste time and could produce inconsistent results.

For milestone 4, FastAPI `BackgroundTasks` starts the work and an in-memory job
registry prevents duplicate jobs in one backend process. This is suitable for a
small local prototype, not durable production processing. A backend restart
clears the registry, so the persisted page states are the source of truth and
the UI can offer to continue unfinished work.

**Decision:** When OCR is disabled, use a provider that fails only when an OCR
page is actually read.

**Reason:** A digital PDF whose pages already contain embedded text should still
be able to reach `text_ready`; it does not require an OCR runtime.

## Mock audio comes before Azure Speech

**Decision:** Milestone 5 creates local mock WAV audio using the Python standard
library before adding Azure Speech.

**Reason:** The listening page, segment ordering, audio metadata, and playback
controls can be tested without paid credentials or vendor-specific failures.
Mock audio is not the final narration; it is a safe development stand-in.

## Azure Speech is behind a provider

**Decision:** Milestone 6 provides both mock speech and Azure Speech
implementations behind one TTS provider boundary, with
`zh-HK-HiuMaanNeural` as the default Hong Kong Cantonese voice.

**Reason:** Local development must work without paid credentials, and speech
vendors should not leak into page or playback code.

**Alternative considered:** Replace mock audio completely with Azure Speech.
That was rejected because it would make basic local development depend on paid
credentials and network access.

## Supabase is postponed

**Decision:** Milestones 1 through 4 have no Supabase runtime package, schema, CLI
setup, or cloud dependency.

**Reason:** Temporary local storage is enough to prove both upload paths. Auth,
Postgres, Storage, and ownership-based Row Level Security will arrive together
in milestone 8, after the core processing model is stable.

## No advanced AI or learning features

**Decision:** Exclude LLM correction, summaries, chat, translation, vocabulary,
flashcards, and synchronized highlighting from the MVP.

**Reason:** Echo's first job is reliable audiobook conversion and listening.
Extra product directions would make that core harder to test and understand.
