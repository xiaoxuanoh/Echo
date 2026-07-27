from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.services.listening_languages import ListeningLanguage


PageClassification = Literal["embedded_text", "requires_ocr"]
PdfClassification = Literal["text", "scanned", "mixed"]
DocumentProcessingStatus = Literal[
    "uploaded",
    "normalizing_pages",
    "inspecting",
    "extracting_text",
    "running_ocr",
    "text_ready",
    "generating_audio",
    "ready",
    "failed",
]
DocumentPageProcessingStatus = Literal[
    "pending",
    "normalizing",
    "extracting",
    "running_ocr",
    "completed",
    "failed",
]


class DocumentPageResult(BaseModel):
    page_id: str
    page_number: int
    original_filename: str | None
    original_image_path: str | None
    processed_image_path: str | None
    extraction_method: Literal["pending", "embedded_text", "ocr"]
    extracted_character_count: int
    rotation_degrees: Literal[0, 90, 180, 270]
    processing_status: Literal["pending", "completed"]


class PdfPageResult(DocumentPageResult):
    classification: PageClassification


class PdfUploadResult(BaseModel):
    book_id: str
    source_type: Literal["pdf"] = "pdf"
    target_language: ListeningLanguage | None
    tts_voice: str | None
    total_pages: int
    original_filename: str
    classification: PdfClassification
    pages: list[PdfPageResult]
    processing_status: Literal["uploaded"] = "uploaded"


class ImagePageResult(DocumentPageResult):
    original_filename: str
    normalized_filename: str


class ImageUploadResult(BaseModel):
    book_id: str
    source_type: Literal["images"] = "images"
    target_language: ListeningLanguage | None
    tts_voice: str | None
    total_pages: int
    ordered_image_filenames: list[str]
    pages: list[ImagePageResult]
    processing_status: Literal["uploaded"] = "uploaded"


class OcrLineResult(BaseModel):
    text: str
    confidence: float


class PageTextPreviewResult(BaseModel):
    book_id: str
    page_id: str
    page_number: int
    provider: Literal["mock", "paddleocr"]
    text: str
    lines: list[OcrLineResult]
    average_confidence: float | None
    processing_time_seconds: float
    preprocessing: Literal["normalized_page"] = "normalized_page"
    persisted: Literal[False] = False


class DocumentPageDetailResult(BaseModel):
    id: UUID
    page_number: int
    original_filename: str | None
    extraction_method: Literal["pending", "embedded_text", "ocr"]
    extracted_text: str
    extracted_character_count: int
    processing_status: DocumentPageProcessingStatus
    error_message: str | None
    updated_at: datetime


class DocumentDetailResult(BaseModel):
    id: UUID
    title: str
    original_filename: str | None
    target_language: ListeningLanguage | None
    tts_voice: str | None
    source_type: Literal["pdf", "images"]
    total_pages: int
    processing_status: DocumentProcessingStatus
    error_message: str | None
    completed_pages: int
    failed_pages: int
    audio_segment_count: int
    processing_active: bool
    pages: list[DocumentPageDetailResult]
    created_at: datetime
    updated_at: datetime


class DocumentLibraryItemResult(BaseModel):
    id: UUID
    library_book_id: UUID
    title: str
    recording_title: str | None
    target_language: ListeningLanguage | None
    tts_voice: str | None
    original_filename: str | None
    source_type: Literal["pdf", "images"]
    total_pages: int
    processing_status: DocumentProcessingStatus
    error_message: str | None
    completed_pages: int
    failed_pages: int
    audio_segment_count: int
    processing_active: bool
    created_at: datetime
    updated_at: datetime


class DocumentLibraryFolderResult(BaseModel):
    id: UUID
    title: str
    recording_count: int
    total_pages: int
    processing_status: DocumentProcessingStatus
    processing_active: bool
    target_languages: list[ListeningLanguage]
    latest_recording_at: datetime
    recordings: list[DocumentLibraryItemResult]


class DocumentLibraryResult(BaseModel):
    folders: list[DocumentLibraryFolderResult]


class DocumentRenameRequest(BaseModel):
    title: str


class DocumentAssignFolderRequest(BaseModel):
    folder_id: UUID


class DocumentMutationResult(BaseModel):
    message: str


class DocumentProcessingAccepted(BaseModel):
    book_id: UUID
    processing_status: Literal["extracting_text", "running_ocr"]
    message: str


class AudioSegmentResult(BaseModel):
    id: UUID
    segment_number: int
    page_id: UUID | None
    page_number: int | None
    source_text: str
    audio_url: str | None
    duration_seconds: float | None
    processing_status: Literal["pending", "generating", "completed", "failed"]
    error_message: str | None


class DocumentAudioResult(BaseModel):
    book_id: UUID
    title: str
    recording_title: str | None
    original_filename: str | None
    target_language: ListeningLanguage | None
    tts_voice: str | None
    processing_status: DocumentProcessingStatus
    processing_active: bool
    segments: list[AudioSegmentResult]


class AudioProcessingAccepted(BaseModel):
    book_id: UUID
    processing_status: Literal["generating_audio"]
    message: str


class HealthResult(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str
