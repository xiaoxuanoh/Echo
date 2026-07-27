from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.listening_languages import ListeningLanguage


DocumentSourceType = Literal["pdf", "images"]
DocumentStatus = Literal[
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
ExtractionMethod = Literal["pending", "embedded_text", "ocr"]
DocumentPageStatus = Literal[
    "pending",
    "normalizing",
    "extracting",
    "running_ocr",
    "completed",
    "failed",
]
AudioSegmentStatus = Literal["pending", "generating", "completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentPageRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    document_id: UUID = Field(alias="book_id", serialization_alias="book_id")
    page_number: int = Field(ge=1)
    original_filename: str | None = None
    original_image_path: str | None = None
    processed_image_path: str | None = None
    extraction_method: ExtractionMethod
    extracted_text: str = ""
    error_message: str | None = None
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    processing_status: DocumentPageStatus
    created_at: datetime
    updated_at: datetime


class AudioSegmentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    document_id: UUID = Field(alias="book_id", serialization_alias="book_id")
    page_id: UUID | None = None
    segment_number: int = Field(ge=1)
    source_text: str
    audio_storage_path: str | None = None
    duration_seconds: float | None = None
    processing_status: AudioSegmentStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    library_document_id: UUID | None = Field(
        default=None,
        alias="library_book_id",
        serialization_alias="library_book_id",
    )
    user_id: UUID | None = None
    title: str
    recording_title: str | None = None
    target_language: ListeningLanguage | None = None
    tts_voice: str | None = None
    original_filename: str | None = None
    source_type: DocumentSourceType
    source_storage_path: str | None = None
    total_pages: int = Field(ge=1)
    status: DocumentStatus
    error_message: str | None = None
    pages: list[DocumentPageRecord]
    audio_segments: list[AudioSegmentRecord] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
