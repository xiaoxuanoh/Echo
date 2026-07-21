# Echo roadmap

## Milestone 1 — Local upload foundation

- Next.js and FastAPI local applications
- PDF and ordered-image upload workflows
- all-page PDF classification
- image normalization and temporary UUID storage
- tests, setup instructions, and environment examples

No OCR, audio, Supabase, authentication, or deployment.

## Milestone 2 — Shared ordered pages

- local book and page metadata
- render scanned PDF pages
- normalize both source types into one page representation

## Milestone 3 — First Traditional Chinese OCR page

- replaceable PaddleOCR service
- one-page quality evaluation
- optional basic preprocessing when evidence supports it

## Milestone 4 — Whole-book text extraction

- process every OCR-required page, including mixed PDFs
- save text and page statuses
- retry handling

## Milestone 5 — Segments and mock listening

- safe text segmentation
- mock audio output
- first listening route and native audio player

## Milestone 6 — Cantonese audio

- Azure Speech provider with configurable `zh-HK` voice
- ordered real audio segments and metadata

## Milestone 7 — Library and progress

- book library and completed listening experience
- saved position and playback speed

## Milestone 8 — Supabase

- Postgres, Storage, and Auth
- ownership-based Row Level Security
- migrate local persistence to cloud-backed storage

## Milestone 9 — Reliability and deployment preparation

- HEIC evaluation
- improved image preprocessing and background processing
- deployment hardening
