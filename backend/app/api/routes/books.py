import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    Path as ApiPath,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.core.errors import EchoError
from app.models.books import BookPageRecord, BookRecord
from app.schemas.books import (
    AudioProcessingAccepted,
    AudioSegmentResult,
    BookAudioResult,
    BookDetailResult,
    BookPageDetailResult,
    BookProcessingAccepted,
    ImagePageResult,
    ImageUploadResult,
    OcrLineResult,
    PageTextPreviewResult,
    PdfPageResult,
    PdfUploadResult,
)
from app.services.book_metadata import LocalBookMetadataService
from app.services.audio_processing import BookAudioProcessingService
from app.services.book_processing import (
    BookTextProcessingService,
    LocalBookJobRegistry,
)
from app.services.image_processing import ImageProcessingService
from app.services.ocr import create_ocr_provider
from app.services.pdf_processing import PdfProcessingService
from app.services.storage import LocalStorageService


router = APIRouter(prefix="/api/books", tags=["books"])


def _page_image_path(book_directory: Path, relative_path: str | None) -> Path:
    if relative_path is None:
        raise EchoError(
            "page_image_unavailable",
            "This page does not have a prepared image to read.",
            status_code=409,
        )
    book_root = book_directory.resolve()
    page_path = (book_directory / relative_path).resolve()
    if not page_path.is_relative_to(book_root):
        raise EchoError(
            "page_image_invalid",
            "The prepared page image path is invalid.",
            status_code=500,
        )
    return page_path


def _processing_service(request: Request) -> BookTextProcessingService:
    settings = request.app.state.settings
    return BookTextProcessingService(
        storage_root=settings.local_storage_path,
        ocr_provider=create_ocr_provider(settings),
    )


def _audio_processing_service(request: Request) -> BookAudioProcessingService:
    settings = request.app.state.settings
    if not settings.use_mock_tts:
        raise EchoError(
            "tts_not_configured",
            "Mock audio is disabled, and real speech is not configured yet.",
            status_code=501,
        )
    return BookAudioProcessingService(
        storage_root=settings.local_storage_path,
        max_segment_characters=settings.tts_segment_max_characters,
    )


def _book_result(
    book: BookRecord,
    *,
    processing_active: bool = False,
) -> BookDetailResult:
    return BookDetailResult(
        id=book.id,
        title=book.title,
        original_filename=book.original_filename,
        source_type=book.source_type,
        total_pages=book.total_pages,
        processing_status=book.status,
        error_message=book.error_message,
        completed_pages=sum(
            page.processing_status == "completed" for page in book.pages
        ),
        failed_pages=sum(page.processing_status == "failed" for page in book.pages),
        audio_segment_count=len(book.audio_segments),
        processing_active=processing_active,
        pages=[
            BookPageDetailResult(
                id=page.id,
                page_number=page.page_number,
                original_filename=page.original_filename,
                extraction_method=page.extraction_method,
                extracted_text=page.extracted_text,
                extracted_character_count=len(page.extracted_text),
                processing_status=page.processing_status,
                error_message=page.error_message,
                updated_at=page.updated_at,
            )
            for page in sorted(book.pages, key=lambda item: item.page_number)
        ],
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _audio_result(
    book: BookRecord,
    *,
    processing_active: bool = False,
) -> BookAudioResult:
    page_numbers_by_id = {page.id: page.page_number for page in book.pages}
    return BookAudioResult(
        book_id=book.id,
        title=book.title,
        processing_status=book.status,
        processing_active=processing_active,
        segments=[
            AudioSegmentResult(
                id=segment.id,
                segment_number=segment.segment_number,
                page_id=segment.page_id,
                page_number=(
                    page_numbers_by_id.get(segment.page_id)
                    if segment.page_id is not None
                    else None
                ),
                source_text=segment.source_text,
                audio_url=(
                    f"/api/books/{book.id}/audio/{segment.segment_number}/file"
                    if segment.audio_storage_path
                    else None
                ),
                duration_seconds=segment.duration_seconds,
                processing_status=segment.processing_status,
                error_message=segment.error_message,
            )
            for segment in sorted(
                book.audio_segments,
                key=lambda item: item.segment_number,
            )
        ],
    )


def _run_book_job(
    service: BookTextProcessingService,
    registry: LocalBookJobRegistry,
    book_id: UUID,
) -> None:
    try:
        service.process_book(book_id)
    finally:
        registry.finish(book_id)


def _run_page_retry(
    service: BookTextProcessingService,
    registry: LocalBookJobRegistry,
    book_id: UUID,
    page_number: int,
) -> None:
    try:
        service.retry_page(book_id, page_number)
    finally:
        registry.finish(book_id)


def _run_audio_job(
    service: BookAudioProcessingService,
    registry: LocalBookJobRegistry,
    book_id: UUID,
) -> None:
    try:
        service.process_audio(book_id)
    finally:
        registry.finish(book_id)


@router.post(
    "/{book_id}/pages/{page_number}/text-preview",
    response_model=PageTextPreviewResult,
)
def preview_page_text(
    request: Request,
    book_id: UUID,
    page_number: int = ApiPath(ge=1),
) -> PageTextPreviewResult:
    settings = request.app.state.settings
    book_directory = settings.local_storage_path / str(book_id)
    book = LocalBookMetadataService().load(book_directory)
    page = next(
        (candidate for candidate in book.pages if candidate.page_number == page_number),
        None,
    )
    if page is None:
        raise EchoError(
            "page_not_found",
            "Echo could not find that page in this temporary book.",
            status_code=404,
        )

    image_path = _page_image_path(book_directory, page.processed_image_path)
    result = create_ocr_provider(settings).read_page(image_path)
    return PageTextPreviewResult(
        book_id=str(book.id),
        page_id=str(page.id),
        page_number=page.page_number,
        provider=result.provider,
        text=result.text,
        lines=[
            OcrLineResult(text=line.text, confidence=line.confidence)
            for line in result.lines
        ],
        average_confidence=result.average_confidence,
        processing_time_seconds=result.processing_time_seconds,
    )


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
        image_service = ImageProcessingService(settings.max_image_pixels)
        normalized_directory = book_directory / "pages"
        normalized_directory.mkdir()
        now = datetime.now(UTC)
        page_records: list[BookPageRecord] = []

        for page in inspection.pages:
            processed_image_path: str | None = None
            extracted_text = ""
            if page.classification == "embedded_text":
                extracted_text = page.extracted_text
            else:
                normalized_filename = f"page-{page.page_number:04d}.png"
                rendered_page = pdf_service.render_page(
                    source_path, page.page_number - 1
                )
                try:
                    image_service.save_rendered_page(
                        rendered_page,
                        normalized_directory / normalized_filename,
                    )
                finally:
                    rendered_page.close()
                processed_image_path = f"pages/{normalized_filename}"

            page_records.append(
                BookPageRecord(
                    id=uuid4(),
                    book_id=book_id,
                    page_number=page.page_number,
                    extraction_method=(
                        "embedded_text"
                        if page.classification == "embedded_text"
                        else "ocr"
                    ),
                    extracted_text=extracted_text,
                    processed_image_path=processed_image_path,
                    processing_status=(
                        "completed"
                        if page.classification == "embedded_text"
                        else "pending"
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )

        metadata = BookRecord(
            id=book_id,
            title=Path(file.filename or "book.pdf").stem or "Untitled book",
            original_filename=file.filename or "book.pdf",
            source_type="pdf",
            source_storage_path="source.pdf",
            total_pages=inspection.total_pages,
            status="uploaded",
            pages=page_records,
            created_at=now,
            updated_at=now,
        )
        LocalBookMetadataService().save(book_directory, metadata)
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
                page_id=str(page_record.id),
                page_number=page.page_number,
                classification=page.classification,
                extracted_character_count=page.extracted_character_count,
                original_filename=None,
                original_image_path=None,
                processed_image_path=page_record.processed_image_path,
                extraction_method=page_record.extraction_method,
                rotation_degrees=0,
                processing_status=page_record.processing_status,
            )
            for page, page_record in zip(inspection.pages, page_records, strict=True)
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
        raise EchoError(
            "invalid_rotations", "The page rotation information is invalid."
        ) from error

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
    page_records: list[BookPageRecord] = []
    now = datetime.now(UTC)

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
            page_id = uuid4()
            page_results.append(
                ImagePageResult(
                    page_id=str(page_id),
                    page_number=index,
                    original_filename=original_filename,
                    normalized_filename=normalized_filename,
                    rotation_degrees=rotation,
                    original_image_path=f"originals/{source_path.name}",
                    processed_image_path=f"pages/{normalized_filename}",
                    extraction_method="ocr",
                    extracted_character_count=0,
                    processing_status="pending",
                )
            )
            page_records.append(
                BookPageRecord(
                    id=page_id,
                    book_id=book_id,
                    page_number=index,
                    original_filename=original_filename,
                    original_image_path=f"originals/{source_path.name}",
                    processed_image_path=f"pages/{normalized_filename}",
                    extraction_method="ocr",
                    rotation_degrees=rotation,
                    processing_status="pending",
                    created_at=now,
                    updated_at=now,
                )
            )

        metadata = BookRecord(
            id=book_id,
            title=(
                Path(page_records[0].original_filename or "Page photo book").stem
                or "Page photo book"
            ),
            source_type="images",
            total_pages=len(page_records),
            status="uploaded",
            pages=page_records,
            created_at=now,
            updated_at=now,
        )
        LocalBookMetadataService().save(book_directory, metadata)
    except Exception:
        shutil.rmtree(book_directory, ignore_errors=True)
        raise

    return ImageUploadResult(
        book_id=str(book_id),
        total_pages=len(page_results),
        ordered_image_filenames=[page.original_filename for page in page_results],
        pages=page_results,
    )


@router.get("/{book_id}", response_model=BookDetailResult)
def get_book(request: Request, book_id: UUID) -> BookDetailResult:
    settings = request.app.state.settings
    book = LocalBookMetadataService().load(settings.local_storage_path / str(book_id))
    registry: LocalBookJobRegistry = request.app.state.book_job_registry
    return _book_result(book, processing_active=registry.is_active(book_id))


@router.get("/{book_id}/audio", response_model=BookAudioResult)
def get_book_audio(request: Request, book_id: UUID) -> BookAudioResult:
    settings = request.app.state.settings
    book = LocalBookMetadataService().load(settings.local_storage_path / str(book_id))
    registry: LocalBookJobRegistry = request.app.state.book_job_registry
    return _audio_result(book, processing_active=registry.is_active(book_id))


@router.post(
    "/{book_id}/prepare-audio",
    response_model=AudioProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def prepare_book_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    book_id: UUID,
) -> AudioProcessingAccepted:
    registry: LocalBookJobRegistry = request.app.state.book_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "book_processing_active",
            "Echo is already preparing this book.",
            status_code=409,
        )
    try:
        service = _audio_processing_service(request)
        book = service.prepare_audio_job(book_id)
    except Exception:
        registry.finish(book_id)
        raise

    background_tasks.add_task(_run_audio_job, service, registry, book_id)
    return AudioProcessingAccepted(
        book_id=book.id,
        processing_status="generating_audio",
        message="Echo has started creating listening audio.",
    )


@router.get("/{book_id}/audio/{segment_number}/file")
def get_audio_file(
    request: Request,
    book_id: UUID,
    segment_number: int = ApiPath(ge=1),
) -> FileResponse:
    settings = request.app.state.settings
    book_directory = settings.local_storage_path / str(book_id)
    book = LocalBookMetadataService().load(book_directory)
    segment = next(
        (
            candidate
            for candidate in book.audio_segments
            if candidate.segment_number == segment_number
        ),
        None,
    )
    if segment is None or segment.audio_storage_path is None:
        raise EchoError(
            "audio_not_found",
            "Echo could not find audio for that segment.",
            status_code=404,
        )

    book_root = book_directory.resolve()
    audio_path = (book_directory / segment.audio_storage_path).resolve()
    if not audio_path.is_relative_to(book_root):
        raise EchoError(
            "audio_path_invalid",
            "The audio file path is invalid.",
            status_code=500,
        )
    if not audio_path.exists():
        raise EchoError(
            "audio_file_missing",
            "Echo could not find the local audio file.",
            status_code=404,
        )
    return FileResponse(audio_path, media_type="audio/wav", filename=audio_path.name)


@router.post(
    "/{book_id}/process-text",
    response_model=BookProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_book_text(
    request: Request,
    background_tasks: BackgroundTasks,
    book_id: UUID,
) -> BookProcessingAccepted:
    registry: LocalBookJobRegistry = request.app.state.book_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "book_processing_active",
            "Echo is already reading this book's page text.",
            status_code=409,
        )
    try:
        service = _processing_service(request)
        book = service.prepare_book_job(book_id)
    except Exception:
        registry.finish(book_id)
        raise

    background_tasks.add_task(_run_book_job, service, registry, book_id)
    return BookProcessingAccepted(
        book_id=book.id,
        processing_status=book.status,
        message="Echo has started reading the page text.",
    )


@router.post(
    "/{book_id}/pages/{page_number}/retry-text",
    response_model=BookProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_page_text(
    request: Request,
    background_tasks: BackgroundTasks,
    book_id: UUID,
    page_number: int = ApiPath(ge=1),
) -> BookProcessingAccepted:
    registry: LocalBookJobRegistry = request.app.state.book_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "book_processing_active",
            "Echo is already reading this book's page text.",
            status_code=409,
        )
    try:
        service = _processing_service(request)
        book = service.prepare_retry_job(book_id, page_number)
    except Exception:
        registry.finish(book_id)
        raise

    background_tasks.add_task(
        _run_page_retry,
        service,
        registry,
        book_id,
        page_number,
    )
    return BookProcessingAccepted(
        book_id=book.id,
        processing_status=book.status,
        message=f"Echo is reading page {page_number} again.",
    )
