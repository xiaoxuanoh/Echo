from typing import Literal

from pydantic import BaseModel


PageClassification = Literal["embedded_text", "requires_ocr"]
PdfClassification = Literal["text", "scanned", "mixed"]


class PdfPageResult(BaseModel):
    page_number: int
    classification: PageClassification
    extracted_character_count: int


class PdfUploadResult(BaseModel):
    book_id: str
    source_type: Literal["pdf"] = "pdf"
    total_pages: int
    original_filename: str
    classification: PdfClassification
    pages: list[PdfPageResult]
    processing_status: Literal["uploaded"] = "uploaded"


class ImagePageResult(BaseModel):
    page_number: int
    original_filename: str
    normalized_filename: str
    rotation_degrees: Literal[0, 90, 180, 270]


class ImageUploadResult(BaseModel):
    book_id: str
    source_type: Literal["images"] = "images"
    total_pages: int
    ordered_image_filenames: list[str]
    pages: list[ImagePageResult]
    processing_status: Literal["uploaded"] = "uploaded"


class HealthResult(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    environment: str
