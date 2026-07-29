import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from datetime import UTC, datetime
from pathlib import Path
import re
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
from fastapi.responses import FileResponse, Response

from app.core.errors import EchoError
from app.models.documents import AudioSegmentRecord, DocumentPageRecord, DocumentRecord
from app.schemas.documents import (
    AudioProcessingAccepted,
    AudioSegmentResult,
    DocumentAudioResult,
    DocumentAssignFolderRequest,
    DocumentDetailResult,
    DocumentLibraryFolderResult,
    DocumentLibraryItemResult,
    DocumentLibraryResult,
    DocumentMutationResult,
    DocumentPageDetailResult,
    DocumentProcessingAccepted,
    DocumentRenameRequest,
    ImagePageResult,
    ImageUploadResult,
    OcrLineResult,
    PageCropRequest,
    PageCropResult,
    PageTextPreviewResult,
    PdfPageResult,
    PdfUploadResult,
)
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.audio_processing import DocumentAudioProcessingService
from app.services.document_processing import (
    DocumentTextProcessingService,
    LocalDocumentJobRegistry,
)
from app.services.image_processing import ImageProcessingService
from app.services.listening_languages import (
    ListeningLanguage,
    resolve_listening_language,
    voice_for_language,
)
from app.services.ocr import create_ocr_provider
from app.services.pdf_processing import PdfProcessingService
from app.services.storage import LocalStorageService
from app.services.tts import create_tts_provider


router = APIRouter(prefix="/api/books", tags=["books"])


def _supabase_auth_enabled(settings: object) -> bool:
    return bool(
        getattr(settings, "supabase_url", "").strip()
        and getattr(settings, "supabase_service_role_key", "").strip()
    )


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    query_token = request.query_params.get("access_token")
    return query_token.strip() if query_token else None


def _verify_supabase_user_id(settings: object, token: str) -> UUID:
    supabase_url = getattr(settings, "supabase_url", "").strip().rstrip("/")
    service_role_key = getattr(settings, "supabase_service_role_key", "").strip()
    request = urllib.request.Request(
        f"{supabase_url}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": service_role_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise EchoError(
            "authentication_required",
            "Sign in again before using your Echo library.",
            status_code=401,
        ) from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise EchoError(
            "authentication_unavailable",
            "Echo could not confirm your account right now.",
            status_code=503,
        ) from error

    user_id = body.get("id")
    if not isinstance(user_id, str):
        raise EchoError(
            "authentication_invalid",
            "Echo could not confirm your account.",
            status_code=401,
        )
    try:
        return UUID(user_id)
    except ValueError as error:
        raise EchoError(
            "authentication_invalid",
            "Echo could not confirm your account.",
            status_code=401,
        ) from error


def _request_user_id(request: Request) -> UUID | None:
    settings = request.app.state.settings
    if not _supabase_auth_enabled(settings):
        return None
    token = _bearer_token(request)
    if token is None:
        raise EchoError(
            "authentication_required",
            "Sign in before using your Echo library.",
            status_code=401,
        )
    return _verify_supabase_user_id(settings, token)


def _authorize_document(book: DocumentRecord, user_id: UUID | None) -> None:
    if user_id is None:
        return
    if book.user_id != user_id:
        raise EchoError(
            "document_not_found",
            "Echo could not find that upload in your library.",
            status_code=404,
        )


def _load_document_for_user(
    storage_root: Path,
    book_id: UUID,
    user_id: UUID | None,
) -> DocumentRecord:
    book = LocalDocumentMetadataService().load(storage_root / str(book_id))
    _authorize_document(book, user_id)
    return book


def _documents_for_user(
    books: list[DocumentRecord],
    user_id: UUID | None,
) -> list[DocumentRecord]:
    if user_id is None:
        return books
    return [book for book in books if book.user_id == user_id]


def _download_filename(value: str | None, fallback: str) -> str:
    if value is None:
        return fallback
    stem = Path(value).stem or value
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return filename or fallback


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


def _document_relative_path(
    book_directory: Path,
    relative_path: str | None,
    *,
    unavailable_code: str,
    unavailable_message: str,
    invalid_code: str,
    invalid_message: str,
) -> Path:
    if relative_path is None:
        raise EchoError(
            unavailable_code,
            unavailable_message,
            status_code=409,
        )
    book_root = book_directory.resolve()
    resolved_path = (book_directory / relative_path).resolve()
    if not resolved_path.is_relative_to(book_root):
        raise EchoError(
            invalid_code,
            invalid_message,
            status_code=500,
        )
    return resolved_path


def _processing_service(request: Request) -> DocumentTextProcessingService:
    settings = request.app.state.settings
    return DocumentTextProcessingService(
        storage_root=settings.local_storage_path,
        ocr_provider=create_ocr_provider(settings),
    )


def _audio_processing_service(request: Request) -> DocumentAudioProcessingService:
    settings = request.app.state.settings
    return DocumentAudioProcessingService(
        storage_root=settings.local_storage_path,
        max_segment_characters=settings.tts_segment_max_characters,
        target_segment_seconds=settings.tts_segment_target_seconds,
        soft_max_segment_seconds=settings.tts_segment_soft_max_seconds,
        min_segment_seconds=settings.tts_segment_min_seconds,
        tts_provider_factory=lambda voice: create_tts_provider(
            settings,
            voice_override=voice,
        ),
    )


def _language_fields(target_language: str | None) -> tuple[ListeningLanguage | None, str | None]:
    language = resolve_listening_language(target_language)
    return language, voice_for_language(language)


def _book_result(
    book: DocumentRecord,
    *,
    processing_active: bool = False,
) -> DocumentDetailResult:
    return DocumentDetailResult(
        id=book.id,
        title=book.title,
        original_filename=book.original_filename,
        target_language=book.target_language,
        tts_voice=book.tts_voice,
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
            DocumentPageDetailResult(
                id=page.id,
                page_number=page.page_number,
                original_filename=page.original_filename,
                extraction_method=page.extraction_method,
                extracted_text=page.extracted_text,
                extracted_character_count=len(page.extracted_text),
                crop_left=page.crop_left,
                crop_top=page.crop_top,
                crop_right=page.crop_right,
                crop_bottom=page.crop_bottom,
                processing_status=page.processing_status,
                error_message=page.error_message,
                updated_at=page.updated_at,
            )
            for page in sorted(book.pages, key=lambda item: item.page_number)
        ],
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _library_item_result(
    book: DocumentRecord,
    *,
    library_book_id: UUID | None = None,
    processing_active: bool = False,
) -> DocumentLibraryItemResult:
    return DocumentLibraryItemResult(
        id=book.id,
        library_book_id=library_book_id or book.library_document_id or book.id,
        title=book.title,
        recording_title=book.recording_title,
        target_language=book.target_language,
        tts_voice=book.tts_voice,
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
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


def _folder_status(recordings: list[DocumentRecord]) -> str:
    statuses = [recording.status for recording in recordings]
    for status_name in (
        "generating_audio",
        "running_ocr",
        "extracting_text",
        "inspecting",
        "normalizing_pages",
    ):
        if status_name in statuses:
            return status_name
    if "failed" in statuses:
        return "failed"
    if "ready" in statuses:
        return "ready"
    if "text_ready" in statuses:
        return "text_ready"
    return statuses[0]


def _library_folders(
    books: list[DocumentRecord],
    registry: LocalDocumentJobRegistry,
) -> list[DocumentLibraryFolderResult]:
    assigned_groups: dict[UUID, list[DocumentRecord]] = {}
    title_groups: dict[str, list[DocumentRecord]] = {}

    for book in books:
        if book.library_document_id is not None and book.library_document_id != book.id:
            assigned_groups.setdefault(book.library_document_id, []).append(book)
        else:
            title_groups.setdefault(book.title.strip().casefold(), []).append(book)

    groups: list[tuple[UUID, list[DocumentRecord]]] = []
    for group_books in title_groups.values():
        folder_id = min(group_books, key=lambda item: item.created_at).id
        recordings = group_books + assigned_groups.pop(folder_id, [])
        groups.append((folder_id, recordings))
    groups.extend(assigned_groups.items())

    folders: list[DocumentLibraryFolderResult] = []
    for folder_id, recordings in groups:
        sorted_recordings = sorted(
            recordings,
            key=lambda item: item.updated_at,
            reverse=True,
        )
        processing_active = any(registry.is_active(recording.id) for recording in recordings)
        target_languages = sorted(
            {
                recording.target_language
                for recording in recordings
                if recording.target_language is not None
            }
        )
        folders.append(
            DocumentLibraryFolderResult(
                id=folder_id,
                title=sorted_recordings[0].title,
                recording_count=len(recordings),
                total_pages=sum(recording.total_pages for recording in recordings),
                processing_status=_folder_status(sorted_recordings),
                processing_active=processing_active,
                target_languages=target_languages,
                latest_recording_at=sorted_recordings[0].updated_at,
                recordings=[
                    _library_item_result(
                        recording,
                        library_book_id=folder_id,
                        processing_active=registry.is_active(recording.id),
                    )
                    for recording in sorted_recordings
                ],
            )
        )

    return sorted(folders, key=lambda folder: folder.latest_recording_at, reverse=True)


def _folder_recordings(
    storage_root: Path,
    folder_id: UUID,
    user_id: UUID | None = None,
) -> list[DocumentRecord]:
    metadata = LocalDocumentMetadataService()
    books = _documents_for_user(metadata.list_documents(storage_root), user_id)
    folders = _library_folders(books, LocalDocumentJobRegistry())
    folder = next((candidate for candidate in folders if candidate.id == folder_id), None)
    if folder is None:
        raise EchoError(
            "library_book_not_found",
            "Echo could not find that local upload folder.",
            status_code=404,
        )
    books_by_id = {book.id: book for book in books}
    return [books_by_id[recording.id] for recording in folder.recordings]


def _target_library_folder(
    storage_root: Path,
    folder_id: UUID,
    user_id: UUID | None = None,
) -> DocumentLibraryFolderResult:
    books = _documents_for_user(
        LocalDocumentMetadataService().list_documents(storage_root),
        user_id,
    )
    folders = _library_folders(books, LocalDocumentJobRegistry())
    folder = next((candidate for candidate in folders if candidate.id == folder_id), None)
    if folder is None:
        raise EchoError(
            "library_book_not_found",
            "Echo could not find that local upload folder.",
            status_code=404,
        )
    return folder


def _ready_audio_segments(book: DocumentRecord) -> list[AudioSegmentRecord]:
    return [
        segment
        for segment in sorted(book.audio_segments, key=lambda item: item.segment_number)
        if segment.processing_status == "completed" and segment.audio_storage_path is not None
    ]


def _write_recording_audio(
    zip_file: zipfile.ZipFile,
    *,
    book_directory: Path,
    book: DocumentRecord,
    archive_directory: str | None = None,
) -> int:
    book_root = book_directory.resolve()
    ready_segments = _ready_audio_segments(book)
    for segment in ready_segments:
        audio_path = (book_directory / str(segment.audio_storage_path)).resolve()
        if not audio_path.is_relative_to(book_root):
            raise EchoError(
                "audio_path_invalid",
                "The audio file path is invalid.",
                status_code=500,
            )
        if not audio_path.exists():
            raise EchoError(
                "audio_file_missing",
                "Echo could not find one of the local audio files.",
                status_code=404,
            )
        extension = audio_path.suffix or ".wav"
        filename = f"part-{segment.segment_number:03d}{extension}"
        arcname = f"{archive_directory}/{filename}" if archive_directory else filename
        zip_file.write(audio_path, arcname=arcname)
    return len(ready_segments)


def _recording_audio_paths(
    *,
    book_directory: Path,
    book: DocumentRecord,
) -> list[Path]:
    book_root = book_directory.resolve()
    audio_paths: list[Path] = []
    for segment in _ready_audio_segments(book):
        audio_path = (book_directory / str(segment.audio_storage_path)).resolve()
        if not audio_path.is_relative_to(book_root):
            raise EchoError(
                "audio_path_invalid",
                "The audio file path is invalid.",
                status_code=500,
            )
        if not audio_path.exists():
            raise EchoError(
                "audio_file_missing",
                "Echo could not find one of the local audio files.",
                status_code=404,
            )
        audio_paths.append(audio_path)
    return audio_paths


def _ffmpeg_concat_line(audio_path: Path) -> str:
    escaped_path = str(audio_path).replace("'", "'\\''")
    return f"file '{escaped_path}'"


def _resolve_ffmpeg_path(ffmpeg_path: str) -> str:
    configured_path = ffmpeg_path.strip() or "ffmpeg"
    if "/" in configured_path:
        return configured_path
    resolved_path = shutil.which(configured_path)
    if resolved_path is not None:
        return resolved_path
    for fallback_path in (
        Path("/opt/homebrew/bin") / configured_path,
        Path("/usr/local/bin") / configured_path,
    ):
        if fallback_path.exists():
            return str(fallback_path)
    return configured_path


def _combine_audio_with_ffmpeg(
    audio_paths: list[Path],
    *,
    ffmpeg_path: str,
) -> bytes:
    if not audio_paths:
        raise EchoError(
            "audio_not_found",
            "Echo could not find audio to download for this upload.",
            status_code=404,
        )

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        list_path = temporary_path / "inputs.txt"
        output_path = temporary_path / "combined.mp3"
        list_path.write_text(
            "\n".join(_ffmpeg_concat_line(audio_path) for audio_path in audio_paths),
            encoding="utf-8",
        )
        command = [
            _resolve_ffmpeg_path(ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as error:
            raise EchoError(
                "ffmpeg_missing",
                "Echo needs ffmpeg installed before it can combine audio into one file.",
                status_code=500,
            ) from error
        except subprocess.CalledProcessError as error:
            raise EchoError(
                "combined_audio_failed",
                "Echo could not combine these recordings into one audio file.",
                status_code=500,
                details={"reason": error.stderr[-500:] if error.stderr else ""},
            ) from error

        if not output_path.exists():
            raise EchoError(
                "combined_audio_missing",
                "Echo could not find the combined audio file.",
                status_code=500,
            )
        combined_audio = output_path.read_bytes()
        if not combined_audio:
            raise EchoError(
                "combined_audio_empty",
                "Echo created an empty combined audio file.",
                status_code=500,
            )
        return combined_audio


def _audio_result(
    book: DocumentRecord,
    *,
    processing_active: bool = False,
) -> DocumentAudioResult:
    page_numbers_by_id = {page.id: page.page_number for page in book.pages}
    return DocumentAudioResult(
        book_id=book.id,
        title=book.title,
        recording_title=book.recording_title,
        original_filename=book.original_filename,
        target_language=book.target_language,
        tts_voice=book.tts_voice,
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
    service: DocumentTextProcessingService,
    registry: LocalDocumentJobRegistry,
    book_id: UUID,
) -> None:
    try:
        service.process_document(book_id)
    finally:
        registry.finish(book_id)


def _run_page_retry(
    service: DocumentTextProcessingService,
    registry: LocalDocumentJobRegistry,
    book_id: UUID,
    page_number: int,
) -> None:
    try:
        service.retry_page(book_id, page_number)
    finally:
        registry.finish(book_id)


def _run_audio_job(
    service: DocumentAudioProcessingService,
    registry: LocalDocumentJobRegistry,
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
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    page = next(
        (candidate for candidate in book.pages if candidate.page_number == page_number),
        None,
    )
    if page is None:
        raise EchoError(
            "page_not_found",
            "Echo could not find that page in this temporary upload.",
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


@router.get("/{book_id}/pages/{page_number}/image")
def get_prepared_page_image(
    request: Request,
    book_id: UUID,
    page_number: int = ApiPath(ge=1),
) -> FileResponse:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    page = next(
        (candidate for candidate in book.pages if candidate.page_number == page_number),
        None,
    )
    if page is None:
        raise EchoError(
            "page_not_found",
            "Echo could not find that page in this temporary upload.",
            status_code=404,
        )

    image_path = _page_image_path(book_directory, page.processed_image_path)
    if not image_path.is_file():
        raise EchoError(
            "page_image_missing",
            "Echo could not find the prepared page image.",
            status_code=404,
        )
    return FileResponse(image_path, media_type="image/png")


@router.put(
    "/{book_id}/pages/{page_number}/crop",
    response_model=PageCropResult,
)
def update_prepared_page_crop(
    request: Request,
    crop: PageCropRequest,
    book_id: UUID,
    page_number: int = ApiPath(ge=1),
) -> PageCropResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    metadata = LocalDocumentMetadataService()
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    page = next(
        (candidate for candidate in book.pages if candidate.page_number == page_number),
        None,
    )
    if page is None:
        raise EchoError(
            "page_not_found",
            "Echo could not find that page in this temporary upload.",
            status_code=404,
        )
    if page.extraction_method != "ocr" or page.processed_image_path is None:
        raise EchoError(
            "page_crop_unavailable",
            "Only pages prepared for OCR can be cropped.",
            status_code=409,
        )
    if book.status != "uploaded" or page.processing_status != "pending":
        raise EchoError(
            "page_crop_not_editable",
            "Crop the page before Echo starts reading its text.",
            status_code=409,
        )

    crop_rectangle = (
        crop.crop_left,
        crop.crop_top,
        crop.crop_right,
        crop.crop_bottom,
    )
    destination = _page_image_path(book_directory, page.processed_image_path)
    image_service = ImageProcessingService(settings.max_image_pixels)

    if page.original_image_path is not None:
        source_path = _document_relative_path(
            book_directory,
            page.original_image_path,
            unavailable_code="page_original_image_unavailable",
            unavailable_message="Echo could not find the original page image.",
            invalid_code="page_original_image_invalid",
            invalid_message="The original page image path is invalid.",
        )
        image_service.normalize_image(
            source_path,
            destination,
            page.rotation_degrees,
            crop_rectangle,
        )
    else:
        source_pdf = _document_relative_path(
            book_directory,
            book.source_storage_path,
            unavailable_code="source_document_unavailable",
            unavailable_message="Echo could not find the original PDF.",
            invalid_code="source_document_invalid",
            invalid_message="The original PDF path is invalid.",
        )
        pdf_service = PdfProcessingService(settings.pdf_text_min_characters)
        rendered_page = pdf_service.render_page(source_pdf, page.page_number - 1)
        try:
            image_service.save_rendered_page(
                rendered_page,
                destination,
                crop_rectangle,
            )
        finally:
            rendered_page.close()

    now = datetime.now(UTC)
    page.crop_left = crop.crop_left
    page.crop_top = crop.crop_top
    page.crop_right = crop.crop_right
    page.crop_bottom = crop.crop_bottom
    page.extracted_text = ""
    page.error_message = None
    page.processing_status = "pending"
    page.updated_at = now
    book.updated_at = now
    metadata.save(book_directory, book)

    return PageCropResult(
        book_id=book.id,
        page_id=page.id,
        page_number=page.page_number,
        crop_left=page.crop_left,
        crop_top=page.crop_top,
        crop_right=page.crop_right,
        crop_bottom=page.crop_bottom,
        processed_image_path=page.processed_image_path,
    )


def _safe_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    return extension if extension in {".jpg", ".jpeg", ".png"} else ".upload"


@router.post("/pdf", response_model=PdfUploadResult)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    library_book_id: UUID | None = Form(default=None),
    target_language: str | None = Form(default=None),
) -> PdfUploadResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book_id = uuid4()
    language, tts_voice = _language_fields(target_language)
    storage = LocalStorageService(settings.local_storage_path)
    target_folder = (
        _target_library_folder(settings.local_storage_path, library_book_id, user_id)
        if library_book_id is not None
        else None
    )
    book_directory = storage.create_document_directory(book_id)
    source_path = book_directory / "source.pdf"

    try:
        await storage.save_upload(file, source_path, settings.max_pdf_size_bytes)
        pdf_service = PdfProcessingService(settings.pdf_text_min_characters)
        inspection = pdf_service.classify_pdf(source_path)
        image_service = ImageProcessingService(settings.max_image_pixels)
        normalized_directory = book_directory / "pages"
        normalized_directory.mkdir()
        now = datetime.now(UTC)
        page_records: list[DocumentPageRecord] = []

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
                DocumentPageRecord(
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

        metadata = DocumentRecord(
            id=book_id,
            library_book_id=target_folder.id if target_folder else book_id,
            user_id=user_id,
            title=(
                target_folder.title
                if target_folder
                else Path(file.filename or "document.pdf").stem or "Untitled document"
            ),
            recording_title=(
                (Path(file.filename or "document.pdf").stem or "Untitled recording")
                if target_folder
                else None
            ),
            target_language=language,
            tts_voice=tts_voice,
            original_filename=file.filename or "document.pdf",
            source_type="pdf",
            source_storage_path="source.pdf",
            total_pages=inspection.total_pages,
            status="uploaded",
            pages=page_records,
            created_at=now,
            updated_at=now,
        )
        LocalDocumentMetadataService().save(book_directory, metadata)
    except Exception:
        shutil.rmtree(book_directory, ignore_errors=True)
        raise

    return PdfUploadResult(
        book_id=str(book_id),
        target_language=language,
        tts_voice=tts_voice,
        total_pages=inspection.total_pages,
        original_filename=file.filename or "document.pdf",
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
                crop_left=page_record.crop_left,
                crop_top=page_record.crop_top,
                crop_right=page_record.crop_right,
                crop_bottom=page_record.crop_bottom,
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
    library_book_id: UUID | None = Form(default=None),
    target_language: str | None = Form(default=None),
) -> ImageUploadResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    language, tts_voice = _language_fields(target_language)
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
    target_folder = (
        _target_library_folder(settings.local_storage_path, library_book_id, user_id)
        if library_book_id is not None
        else None
    )
    book_directory = storage.create_document_directory(book_id)
    originals_directory = book_directory / "originals"
    normalized_directory = book_directory / "pages"
    originals_directory.mkdir()
    normalized_directory.mkdir()
    image_service = ImageProcessingService(settings.max_image_pixels)
    page_results: list[ImagePageResult] = []
    page_records: list[DocumentPageRecord] = []
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
                    crop_left=None,
                    crop_top=None,
                    crop_right=None,
                    crop_bottom=None,
                    processing_status="pending",
                )
            )
            page_records.append(
                DocumentPageRecord(
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

        metadata = DocumentRecord(
            id=book_id,
            library_book_id=target_folder.id if target_folder else book_id,
            user_id=user_id,
            title=(
                target_folder.title
                if target_folder
                else Path(page_records[0].original_filename or "Page photo document").stem
                or "Page photo document"
            ),
            recording_title=(
                (
                    Path(page_records[0].original_filename or "Page photos").stem
                    or "Page photos"
                )
                if target_folder
                else None
            ),
            target_language=language,
            tts_voice=tts_voice,
            source_type="images",
            total_pages=len(page_records),
            status="uploaded",
            pages=page_records,
            created_at=now,
            updated_at=now,
        )
        LocalDocumentMetadataService().save(book_directory, metadata)
    except Exception:
        shutil.rmtree(book_directory, ignore_errors=True)
        raise

    return ImageUploadResult(
        book_id=str(book_id),
        target_language=language,
        tts_voice=tts_voice,
        total_pages=len(page_results),
        ordered_image_filenames=[page.original_filename for page in page_results],
        pages=page_results,
    )


@router.get("", response_model=DocumentLibraryResult)
def list_documents(request: Request) -> DocumentLibraryResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
    books = _documents_for_user(
        LocalDocumentMetadataService().list_documents(settings.local_storage_path),
        user_id,
    )
    return DocumentLibraryResult(folders=_library_folders(books, registry))


@router.patch("/{book_id}/folder", response_model=DocumentMutationResult)
def assign_recording_to_folder(
    request: Request,
    book_id: UUID,
    payload: DocumentAssignFolderRequest,
) -> DocumentMutationResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    metadata = LocalDocumentMetadataService()
    book_directory = settings.local_storage_path / str(book_id)
    recording = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    target_folder = _target_library_folder(
        settings.local_storage_path,
        payload.folder_id,
        user_id,
    )

    recording.library_document_id = target_folder.id
    recording.title = target_folder.title
    if recording.recording_title is None:
        recording.recording_title = (
            Path(recording.original_filename or "Recording").stem or "Recording"
        )
    recording.updated_at = datetime.now(UTC)
    metadata.save(book_directory, recording)
    return DocumentMutationResult(message="Echo saved this recording to the folder.")


@router.patch("/folders/{folder_id}", response_model=DocumentMutationResult)
def rename_book_folder(
    request: Request,
    folder_id: UUID,
    payload: DocumentRenameRequest,
) -> DocumentMutationResult:
    title = payload.title.strip()
    if not title:
        raise EchoError(
            "book_title_required",
            "Enter a name for this book.",
            status_code=422,
        )

    settings = request.app.state.settings
    user_id = _request_user_id(request)
    metadata = LocalDocumentMetadataService()
    now = datetime.now(UTC)
    for recording in _folder_recordings(settings.local_storage_path, folder_id, user_id):
        recording.title = title
        recording.library_document_id = folder_id
        recording.updated_at = now
        metadata.save(settings.local_storage_path / str(recording.id), recording)

    return DocumentMutationResult(message="Echo renamed this local upload.")


@router.delete("/folders/{folder_id}", response_model=DocumentMutationResult)
def delete_book_folder(request: Request, folder_id: UUID) -> DocumentMutationResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    for recording in _folder_recordings(settings.local_storage_path, folder_id, user_id):
        shutil.rmtree(settings.local_storage_path / str(recording.id), ignore_errors=True)

    return DocumentMutationResult(message="Echo removed this local upload.")


@router.get("/folders/{folder_id}/audio/download")
def download_folder_audio(request: Request, folder_id: UUID) -> Response:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    recordings = sorted(
        _folder_recordings(settings.local_storage_path, folder_id, user_id),
        key=lambda recording: recording.created_at,
    )
    audio_paths = [
        audio_path
        for recording in recordings
        for audio_path in _recording_audio_paths(
            book_directory=settings.local_storage_path / str(recording.id),
            book=recording,
        )
    ]

    folder = _target_library_folder(settings.local_storage_path, folder_id, user_id)
    combined_audio = _combine_audio_with_ffmpeg(
        audio_paths,
        ffmpeg_path=settings.ffmpeg_path,
    )
    filename = _download_filename(folder.title, "echo-upload-audio")
    return Response(
        content=combined_audio,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.mp3"',
        },
    )


@router.delete("/{book_id}", response_model=DocumentMutationResult)
def delete_recording(request: Request, book_id: UUID) -> DocumentMutationResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    _load_document_for_user(settings.local_storage_path, book_id, user_id)
    shutil.rmtree(book_directory, ignore_errors=True)
    return DocumentMutationResult(message="Echo removed this recording.")


@router.patch("/{book_id}", response_model=DocumentMutationResult)
def rename_recording(
    request: Request,
    book_id: UUID,
    payload: DocumentRenameRequest,
) -> DocumentMutationResult:
    title = payload.title.strip()
    if not title:
        raise EchoError(
            "recording_title_required",
            "Enter a name for this recording.",
            status_code=422,
        )

    settings = request.app.state.settings
    user_id = _request_user_id(request)
    metadata = LocalDocumentMetadataService()
    book_directory = settings.local_storage_path / str(book_id)
    recording = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    recording.recording_title = title
    recording.updated_at = datetime.now(UTC)
    metadata.save(book_directory, recording)
    return DocumentMutationResult(message="Echo renamed this recording.")


@router.get("/{book_id}", response_model=DocumentDetailResult)
def get_book(request: Request, book_id: UUID) -> DocumentDetailResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
    return _book_result(book, processing_active=registry.is_active(book_id))


@router.get("/{book_id}/audio", response_model=DocumentAudioResult)
def get_book_audio(request: Request, book_id: UUID) -> DocumentAudioResult:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
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
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    _load_document_for_user(settings.local_storage_path, book_id, user_id)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "document_processing_active",
            "Echo is already preparing this upload.",
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
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
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
    media_type = "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(audio_path, media_type=media_type, filename=audio_path.name)


@router.get("/{book_id}/audio/download")
def download_recording_audio(request: Request, book_id: UUID) -> Response:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    book_directory = settings.local_storage_path / str(book_id)
    book = _load_document_for_user(settings.local_storage_path, book_id, user_id)
    if not _ready_audio_segments(book):
        raise EchoError(
            "audio_not_found",
            "Echo could not find audio to download for this recording.",
            status_code=404,
        )

    archive = BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        _write_recording_audio(zip_file, book_directory=book_directory, book=book)

    filename = _download_filename(
        book.recording_title or book.original_filename or book.title,
        "echo-recording-audio",
    )
    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.zip"',
        },
    )


@router.post(
    "/{book_id}/process-text",
    response_model=DocumentProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_book_text(
    request: Request,
    background_tasks: BackgroundTasks,
    book_id: UUID,
) -> DocumentProcessingAccepted:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    _load_document_for_user(settings.local_storage_path, book_id, user_id)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "document_processing_active",
            "Echo is already reading this upload's page text.",
            status_code=409,
        )
    try:
        service = _processing_service(request)
        book = service.prepare_document_job(book_id)
    except Exception:
        registry.finish(book_id)
        raise

    background_tasks.add_task(_run_book_job, service, registry, book_id)
    return DocumentProcessingAccepted(
        book_id=book.id,
        processing_status=book.status,
        message="Echo has started reading the page text.",
    )


@router.post(
    "/{book_id}/pages/{page_number}/retry-text",
    response_model=DocumentProcessingAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_page_text(
    request: Request,
    background_tasks: BackgroundTasks,
    book_id: UUID,
    page_number: int = ApiPath(ge=1),
) -> DocumentProcessingAccepted:
    settings = request.app.state.settings
    user_id = _request_user_id(request)
    _load_document_for_user(settings.local_storage_path, book_id, user_id)
    registry: LocalDocumentJobRegistry = request.app.state.document_job_registry
    if not registry.start(book_id):
        raise EchoError(
            "document_processing_active",
            "Echo is already reading this upload's page text.",
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
    return DocumentProcessingAccepted(
        book_id=book.id,
        processing_status=book.status,
        message=f"Echo is reading page {page_number} again.",
    )
