from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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
    crop_left: float | None = None
    crop_top: float | None = None
    crop_right: float | None = None
    crop_bottom: float | None = None
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
    warnings: list[str] = Field(default_factory=list)
    preprocessing: Literal["normalized_page"] = "normalized_page"
    persisted: Literal[False] = False


class PageCropRequest(BaseModel):
    crop_left: float = Field(ge=0, le=1)
    crop_top: float = Field(ge=0, le=1)
    crop_right: float = Field(ge=0, le=1)
    crop_bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_crop_area(self) -> "PageCropRequest":
        if self.crop_left >= self.crop_right or self.crop_top >= self.crop_bottom:
            raise ValueError("Crop bounds must describe a visible area.")
        return self


class PageCropResult(BaseModel):
    book_id: UUID
    page_id: UUID
    page_number: int
    crop_left: float
    crop_top: float
    crop_right: float
    crop_bottom: float
    processed_image_path: str


class DocumentPageDetailResult(BaseModel):
    id: UUID
    page_number: int
    original_filename: str | None
    extraction_method: Literal["pending", "embedded_text", "ocr"]
    extracted_text: str
    extracted_character_count: int
    crop_left: float | None
    crop_top: float | None
    crop_right: float | None
    crop_bottom: float | None
    processing_status: DocumentPageProcessingStatus
    error_message: str | None
    warning_messages: list[str] = Field(default_factory=list)
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


class PageTextUpdateRequest(BaseModel):
    text: str


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
