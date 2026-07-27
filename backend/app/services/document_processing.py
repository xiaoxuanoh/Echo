import logging
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.core.errors import EchoError
from app.models.documents import DocumentPageRecord, DocumentRecord
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.ocr import OcrProvider


logger = logging.getLogger(__name__)


class LocalDocumentJobRegistry:
    """Prevents duplicate local jobs without pretending to be a durable queue."""

    def __init__(self) -> None:
        self._active_documents: set[UUID] = set()
        self._lock = Lock()

    def start(self, document_id: UUID) -> bool:
        with self._lock:
            if document_id in self._active_documents:
                return False
            self._active_documents.add(document_id)
            return True

    def finish(self, document_id: UUID) -> None:
        with self._lock:
            self._active_documents.discard(document_id)

    def is_active(self, document_id: UUID) -> bool:
        with self._lock:
            return document_id in self._active_documents


class DocumentTextProcessingService:
    """Coordinates page text extraction while persisting each state transition."""

    def __init__(
        self,
        *,
        storage_root: Path,
        ocr_provider: OcrProvider,
        metadata: LocalDocumentMetadataService | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.ocr_provider = ocr_provider
        self.metadata = metadata or LocalDocumentMetadataService()

    def document_directory(self, document_id: UUID) -> Path:
        return self.storage_root / str(document_id)

    def load_document(self, document_id: UUID) -> DocumentRecord:
        return self.metadata.load(self.document_directory(document_id))

    def prepare_document_job(self, document_id: UUID) -> DocumentRecord:
        document = self.load_document(document_id)
        pending_pages = [
            page
            for page in document.pages
            if page.processing_status in {"pending", "running_ocr", "extracting"}
        ]
        if document.status == "text_ready":
            raise EchoError(
                "book_text_ready",
                "This document's page text is already prepared.",
                status_code=409,
            )
        if not pending_pages and any(
            page.processing_status == "failed" for page in document.pages
        ):
            raise EchoError(
                "failed_pages_require_retry",
                "Retry the pages that still need attention.",
                status_code=409,
            )

        now = datetime.now(UTC)
        document.status = (
            "running_ocr"
            if any(page.extraction_method == "ocr" for page in pending_pages)
            else "extracting_text"
        )
        document.error_message = None
        document.updated_at = now
        self.metadata.save(self.document_directory(document_id), document)
        return document

    def prepare_retry_job(self, document_id: UUID, page_number: int) -> DocumentRecord:
        document = self.load_document(document_id)
        page = self._find_page(document, page_number)
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
        document.status = (
            "running_ocr" if page.extraction_method == "ocr" else "extracting_text"
        )
        document.error_message = None
        document.updated_at = now
        self.metadata.save(self.document_directory(document_id), document)
        return document

    def process_document(self, document_id: UUID) -> None:
        document = self.load_document(document_id)
        for page in sorted(document.pages, key=lambda item: item.page_number):
            if page.processing_status not in {"pending", "running_ocr", "extracting"}:
                continue
            if page.extraction_method == "embedded_text":
                self._complete_embedded_page(document, page)
            else:
                self._process_ocr_page(document, page)
        self._finalize_document(document)

    def retry_page(self, document_id: UUID, page_number: int) -> None:
        document = self.load_document(document_id)
        page = self._find_page(document, page_number)
        if page.processing_status != "pending":
            return
        if page.extraction_method == "embedded_text":
            self._complete_embedded_page(document, page)
        else:
            self._process_ocr_page(document, page)
        self._finalize_document(document)

    def _complete_embedded_page(
        self,
        document: DocumentRecord,
        page: DocumentPageRecord,
    ) -> None:
        if page.extracted_text.strip():
            page.processing_status = "completed"
            page.error_message = None
        else:
            page.processing_status = "failed"
            page.error_message = "Echo could not find readable text on this page."
        page.updated_at = datetime.now(UTC)
        document.updated_at = page.updated_at
        self.metadata.save(self.document_directory(document.id), document)

    def _process_ocr_page(self, document: DocumentRecord, page: DocumentPageRecord) -> None:
        page.processing_status = "running_ocr"
        page.error_message = None
        page.updated_at = datetime.now(UTC)
        document.status = "running_ocr"
        document.updated_at = page.updated_at
        self.metadata.save(self.document_directory(document.id), document)

        try:
            image_path = self._safe_page_path(document.id, page.processed_image_path)
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
                "Page text reading failed for document %s page %s: %s",
                document.id,
                page.page_number,
                error.code,
            )
        except Exception:
            page.processing_status = "failed"
            page.error_message = "Echo could not read the text on this page."
            logger.exception(
                "Unexpected page text failure for document %s page %s",
                document.id,
                page.page_number,
            )

        page.updated_at = datetime.now(UTC)
        document.updated_at = page.updated_at
        self.metadata.save(self.document_directory(document.id), document)

    def _finalize_document(self, document: DocumentRecord) -> None:
        failed_pages = [
            page for page in document.pages if page.processing_status == "failed"
        ]
        if failed_pages:
            document.status = "failed"
            document.error_message = (
                f"{len(failed_pages)} page"
                f"{'s' if len(failed_pages) != 1 else ''} still need attention."
            )
        elif all(page.processing_status == "completed" for page in document.pages):
            document.status = "text_ready"
            document.error_message = None
        else:
            document.status = "extracting_text"
            document.error_message = None
        document.updated_at = datetime.now(UTC)
        self.metadata.save(self.document_directory(document.id), document)

    @staticmethod
    def _find_page(document: DocumentRecord, page_number: int) -> DocumentPageRecord:
        page = next(
            (item for item in document.pages if item.page_number == page_number),
            None,
        )
        if page is None:
            raise EchoError(
                "page_not_found",
                "Echo could not find that page in this temporary document.",
                status_code=404,
            )
        return page

    def _safe_page_path(self, document_id: UUID, relative_path: str | None) -> Path:
        if relative_path is None:
            raise EchoError(
                "page_image_unavailable",
                "This page does not have a prepared image to read.",
                status_code=409,
            )
        document_root = self.document_directory(document_id).resolve()
        page_path = (document_root / relative_path).resolve()
        if not page_path.is_relative_to(document_root):
            raise EchoError(
                "page_image_invalid",
                "The prepared page image path is invalid.",
                status_code=500,
            )
        return page_path
