from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


BookSourceType = Literal["pdf", "images"]
BookStatus = Literal[
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
PageStatus = Literal[
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


class BookPageRecord(BaseModel):
    id: UUID
    book_id: UUID
    page_number: int = Field(ge=1)
    original_filename: str | None = None
    original_image_path: str | None = None
    processed_image_path: str | None = None
    extraction_method: ExtractionMethod
    extracted_text: str = ""
    error_message: str | None = None
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    processing_status: PageStatus
    created_at: datetime
    updated_at: datetime


class AudioSegmentRecord(BaseModel):
    id: UUID
    book_id: UUID
    page_id: UUID | None = None
    segment_number: int = Field(ge=1)
    source_text: str
    audio_storage_path: str | None = None
    duration_seconds: float | None = None
    processing_status: AudioSegmentStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BookRecord(BaseModel):
    id: UUID
    library_book_id: UUID | None = None
    user_id: UUID | None = None
    title: str
    recording_title: str | None = None
    original_filename: str | None = None
    source_type: BookSourceType
    source_storage_path: str | None = None
    total_pages: int = Field(ge=1)
    status: BookStatus
    error_message: str | None = None
    pages: list[BookPageRecord]
    audio_segments: list[AudioSegmentRecord] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
