from typing import Literal

from pydantic import BaseModel


PageClassification = Literal["embedded_text", "requires_ocr"]
PdfClassification = Literal["text", "scanned", "mixed"]


class BookPageResult(BaseModel):
    page_id: str
    page_number: int
    original_filename: str | None
    original_image_path: str | None
    processed_image_path: str | None
    extraction_method: Literal["pending", "embedded_text", "ocr"]
    extracted_character_count: int
    rotation_degrees: Literal[0, 90, 180, 270]
    processing_status: Literal["pending", "completed"]


class PdfPageResult(BookPageResult):
    classification: PageClassification


class PdfUploadResult(BaseModel):
    book_id: str
    source_type: Literal["pdf"] = "pdf"
    total_pages: int
    original_filename: str
    classification: PdfClassification
    pages: list[PdfPageResult]
    processing_status: Literal["uploaded"] = "uploaded"


class ImagePageResult(BookPageResult):
    original_filename: str
    normalized_filename: str


class ImageUploadResult(BaseModel):
    book_id: str
    source_type: Literal["images"] = "images"
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


class HealthResult(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str
