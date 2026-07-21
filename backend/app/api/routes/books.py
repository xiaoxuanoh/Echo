import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.errors import EchoError
from app.schemas.books import (
    ImagePageResult,
    ImageUploadResult,
    PdfPageResult,
    PdfUploadResult,
)
from app.services.image_processing import ImageProcessingService
from app.services.pdf_processing import PdfProcessingService
from app.services.storage import LocalStorageService


router = APIRouter(prefix="/api/books", tags=["books"])


def _safe_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    return extension if extension in {".jpg", ".jpeg", ".png"} else ".upload"


@router.post("/pdf", response_model=PdfUploadResult)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
) -> PdfUploadResult:
    settings = request.app.state.settings
    book_id = uuid4()
    storage = LocalStorageService(settings.local_storage_path)
    book_directory = storage.create_book_directory(book_id)
    source_path = book_directory / "source.pdf"

    try:
        await storage.save_upload(file, source_path, settings.max_pdf_size_bytes)
        pdf_service = PdfProcessingService(settings.pdf_text_min_characters)
        inspection = pdf_service.classify_pdf(source_path)
    except Exception:
        shutil.rmtree(book_directory, ignore_errors=True)
        raise

    return PdfUploadResult(
        book_id=str(book_id),
        total_pages=inspection.total_pages,
        original_filename=file.filename or "book.pdf",
        classification=inspection.classification,
        pages=[
            PdfPageResult(
                page_number=page.page_number,
                classification=page.classification,
                extracted_character_count=page.extracted_character_count,
            )
            for page in inspection.pages
        ],
    )


@router.post("/images", response_model=ImageUploadResult)
async def upload_images(
    request: Request,
    files: list[UploadFile] = File(...),
    rotations: str = Form(...),
) -> ImageUploadResult:
    settings = request.app.state.settings
    if not files:
        raise EchoError("no_images", "Please add at least one page image.")
    if len(files) > settings.max_image_upload_count:
        raise EchoError(
            "too_many_images",
            "Too many page images were selected.",
            status_code=413,
            details={"max_count": settings.max_image_upload_count},
        )

    try:
        parsed_rotations = json.loads(rotations)
    except json.JSONDecodeError as error:
        raise EchoError("invalid_rotations", "The page rotation information is invalid.") from error

    if not isinstance(parsed_rotations, list) or len(parsed_rotations) != len(files):
        raise EchoError(
            "invalid_rotations",
            "Each uploaded page must have one rotation value.",
        )
    if any(
        not isinstance(rotation, int) or rotation not in {0, 90, 180, 270}
        for rotation in parsed_rotations
    ):
        raise EchoError(
            "invalid_rotation",
            "Page rotation must be 0, 90, 180, or 270 degrees.",
        )

    book_id = uuid4()
    storage = LocalStorageService(settings.local_storage_path)
    book_directory = storage.create_book_directory(book_id)
    originals_directory = book_directory / "originals"
    normalized_directory = book_directory / "pages"
    originals_directory.mkdir()
    normalized_directory.mkdir()
    image_service = ImageProcessingService(settings.max_image_pixels)
    page_results: list[ImagePageResult] = []

    try:
        for index, (upload, rotation) in enumerate(
            zip(files, parsed_rotations, strict=True), start=1
        ):
            original_filename = upload.filename or f"page-{index}"
            source_path = originals_directory / (
                f"original-{index:04d}{_safe_extension(original_filename)}"
            )
            await storage.save_upload(
                upload,
                source_path,
                settings.max_image_size_bytes,
            )
            image_service.validate_image(source_path)
            normalized_filename = f"page-{index:04d}.png"
            image_service.normalize_image(
                source_path,
                normalized_directory / normalized_filename,
                rotation,
            )
            page_results.append(
                ImagePageResult(
                    page_number=index,
                    original_filename=original_filename,
                    normalized_filename=normalized_filename,
                    rotation_degrees=rotation,
                )
            )
    except Exception:
        shutil.rmtree(book_directory, ignore_errors=True)
        raise


    return ImageUploadResult(
        book_id=str(book_id),
        total_pages=len(page_results),
        ordered_image_filenames=[page.original_filename for page in page_results],
        pages=page_results,
    )
