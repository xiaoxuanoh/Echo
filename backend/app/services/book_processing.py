import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.core.errors import EchoError
from app.models.books import BookPageRecord, BookRecord
from app.services.book_metadata import LocalBookMetadataService
from app.services.ocr import OcrProvider


logger = logging.getLogger(__name__)


class LocalBookJobRegistry:
    """Prevents duplicate local jobs without pretending to be a durable queue."""

    def __init__(self) -> None:
        self._active_books: set[UUID] = set()
        self._lock = Lock()

    def start(self, book_id: UUID) -> bool:
        with self._lock:
            if book_id in self._active_books:
                return False
            self._active_books.add(book_id)
            return True

    def finish(self, book_id: UUID) -> None:
        with self._lock:
            self._active_books.discard(book_id)

    def is_active(self, book_id: UUID) -> bool:
        with self._lock:
            return book_id in self._active_books


class BookTextProcessingService:
    """Coordinates page text extraction while persisting each state transition."""

    def __init__(
        self,
        *,
        storage_root: Path,
        ocr_provider: OcrProvider,
        metadata: LocalBookMetadataService | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.ocr_provider = ocr_provider
        self.metadata = metadata or LocalBookMetadataService()

    def book_directory(self, book_id: UUID) -> Path:
        return self.storage_root / str(book_id)

    def load_book(self, book_id: UUID) -> BookRecord:
        return self.metadata.load(self.book_directory(book_id))

    def prepare_book_job(self, book_id: UUID) -> BookRecord:
        book = self.load_book(book_id)
        pending_pages = [
            page
            for page in book.pages
            if page.processing_status in {"pending", "running_ocr", "extracting"}
        ]
        if book.status == "text_ready":
            raise EchoError(
                "book_text_ready",
                "This book's page text is already prepared.",
                status_code=409,
            )
        if not pending_pages and any(
            page.processing_status == "failed" for page in book.pages
        ):
            raise EchoError(
                "failed_pages_require_retry",
                "Retry the pages that still need attention.",
                status_code=409,
            )

        now = datetime.now(UTC)
        book.status = (
            "running_ocr"
            if any(page.extraction_method == "ocr" for page in pending_pages)
            else "extracting_text"
        )
        book.error_message = None
        book.updated_at = now
        self.metadata.save(self.book_directory(book_id), book)
        return book

    def prepare_retry_job(self, book_id: UUID, page_number: int) -> BookRecord:
        book = self.load_book(book_id)
        page = self._find_page(book, page_number)
        if page.processing_status != "failed":
            raise EchoError(
                "page_not_failed",
                "Only a page that needs attention can be retried.",
                status_code=409,
            )
        now = datetime.now(UTC)
        page.processing_status = "pending"
        page.error_message = None
        page.updated_at = now
        book.status = (
            "running_ocr" if page.extraction_method == "ocr" else "extracting_text"
        )
        book.error_message = None
        book.updated_at = now
        self.metadata.save(self.book_directory(book_id), book)
        return book

    def process_book(self, book_id: UUID) -> None:
        book = self.load_book(book_id)
        for page in sorted(book.pages, key=lambda item: item.page_number):
            if page.processing_status not in {"pending", "running_ocr", "extracting"}:
                continue
            if page.extraction_method == "embedded_text":
                self._complete_embedded_page(book, page)
            else:
                self._process_ocr_page(book, page)
        self._finalize_book(book)

    def retry_page(self, book_id: UUID, page_number: int) -> None:
        book = self.load_book(book_id)
        page = self._find_page(book, page_number)
        if page.processing_status != "pending":
            return
        if page.extraction_method == "embedded_text":
            self._complete_embedded_page(book, page)
        else:
            self._process_ocr_page(book, page)
        self._finalize_book(book)

    def _complete_embedded_page(
        self,
        book: BookRecord,
        page: BookPageRecord,
    ) -> None:
        if page.extracted_text.strip():
            page.processing_status = "completed"
            page.error_message = None
        else:
            page.processing_status = "failed"
            page.error_message = "Echo could not find readable text on this page."
        page.updated_at = datetime.now(UTC)
        book.updated_at = page.updated_at
        self.metadata.save(self.book_directory(book.id), book)

    def _process_ocr_page(self, book: BookRecord, page: BookPageRecord) -> None:
        page.processing_status = "running_ocr"
        page.error_message = None
        page.updated_at = datetime.now(UTC)
        book.status = "running_ocr"
        book.updated_at = page.updated_at
        self.metadata.save(self.book_directory(book.id), book)

        try:
            image_path = self._safe_page_path(book.id, page.processed_image_path)
            result = self.ocr_provider.read_page(image_path)
            if not result.text.strip():
                raise EchoError(
                    "no_page_text",
                    "Echo could not find readable text on this page.",
                )
            page.extracted_text = result.text
            page.processing_status = "completed"
            page.error_message = None
        except EchoError as error:
            page.processing_status = "failed"
            page.error_message = error.message
            logger.warning(
                "Page text reading failed for book %s page %s: %s",
                book.id,
                page.page_number,
                error.code,
            )
        except Exception:
            page.processing_status = "failed"
            page.error_message = "Echo could not read the text on this page."
            logger.exception(
                "Unexpected page text failure for book %s page %s",
                book.id,
                page.page_number,
            )

        page.updated_at = datetime.now(UTC)
        book.updated_at = page.updated_at
        self.metadata.save(self.book_directory(book.id), book)

    def _finalize_book(self, book: BookRecord) -> None:
        failed_pages = [
            page for page in book.pages if page.processing_status == "failed"
        ]
        if failed_pages:
            book.status = "failed"
            book.error_message = (
                f"{len(failed_pages)} page"
                f"{'s' if len(failed_pages) != 1 else ''} still need attention."
            )
        elif all(page.processing_status == "completed" for page in book.pages):
            book.status = "text_ready"
            book.error_message = None
        else:
            book.status = "extracting_text"
            book.error_message = None
        book.updated_at = datetime.now(UTC)
        self.metadata.save(self.book_directory(book.id), book)

    @staticmethod
    def _find_page(book: BookRecord, page_number: int) -> BookPageRecord:
        page = next(
            (item for item in book.pages if item.page_number == page_number),
            None,
        )
        if page is None:
            raise EchoError(
                "page_not_found",
                "Echo could not find that page in this temporary book.",
                status_code=404,
            )
        return page

    def _safe_page_path(self, book_id: UUID, relative_path: str | None) -> Path:
        if relative_path is None:
            raise EchoError(
                "page_image_unavailable",
                "This page does not have a prepared image to read.",
                status_code=409,
            )
        book_root = self.book_directory(book_id).resolve()
        page_path = (book_root / relative_path).resolve()
        if not page_path.is_relative_to(book_root):
            raise EchoError(
                "page_image_invalid",
                "The prepared page image path is invalid.",
                status_code=500,
            )
        return page_path
