import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID

from app.core.errors import EchoError
from app.models.documents import DocumentPageRecord, DocumentRecord
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.ocr import OcrProvider


logger = logging.getLogger(__name__)


ISOLATED_PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:[-–—]\s*)?(?:(?:page|p)\.?\s*|頁\s*|第\s*)?\d{1,4}(?:\s*頁)?(?:\s*[-–—])?$",
    re.IGNORECASE,
)
RUNNING_HEADER_PATTERN = re.compile(
    r"^(?:chapter\s+\d+|第\s*[一二三四五六七八九十百\d]+\s*[章章节節]).{0,30}$",
    re.IGNORECASE,
)
CHART_START_PATTERN = re.compile(
    r"^(?:圖|图|figure|fig\.?|chart)\s*\d+(?:[.\-]\d+)?\s*[:：]?.*",
    re.IGNORECASE,
)
CHART_SOURCE_PATTERN = re.compile(
    r"^(?:資料來源|资料来源|來源|来源|source)\s*[:：]?.*",
    re.IGNORECASE,
)
CHART_SHORT_LABEL_PATTERN = re.compile(
    r"^[\w\s().,%/+-]*$",
    re.IGNORECASE,
)
CHART_PLACEHOLDERS = {
    "cantonese": "此處有一個圖表。",
    "mandarin": "此处有一个图表。",
    "english": "There is a chart here.",
}


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
            page.extracted_text = self._clean_ocr_text(
                result.text,
                target_language=document.target_language,
            )
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

    @staticmethod
    def _remove_isolated_page_number_lines(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = [
            line
            for line in lines
            if not ISOLATED_PAGE_NUMBER_PATTERN.fullmatch(line.strip())
        ]
        return "\n".join(cleaned_lines).strip()

    @classmethod
    def _clean_ocr_text(
        cls,
        text: str,
        *,
        target_language: str | None,
    ) -> str:
        lines = cls._remove_running_headers(
            cls._remove_isolated_page_number_lines(text).splitlines()
        )
        cleaned_lines = cls._replace_chart_blocks(lines, target_language=target_language)
        return "\n".join(line for line in cleaned_lines if line.strip()).strip()

    @staticmethod
    def _remove_running_headers(lines: list[str]) -> list[str]:
        cleaned = list(lines)
        for index in (0, len(cleaned) - 1):
            if not cleaned:
                break
            line = cleaned[index].strip()
            if RUNNING_HEADER_PATTERN.fullmatch(line):
                cleaned[index] = ""
        return [line for line in cleaned if line.strip()]

    @classmethod
    def _replace_chart_blocks(
        cls,
        lines: list[str],
        *,
        target_language: str | None,
    ) -> list[str]:
        output: list[str] = []
        in_chart_block = False
        placeholder = cls._chart_placeholder(target_language)

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if CHART_START_PATTERN.match(stripped):
                if not output or output[-1] != placeholder:
                    output.append(placeholder)
                in_chart_block = True
                continue

            if in_chart_block and cls._is_probable_chart_support_line(stripped):
                continue

            in_chart_block = False
            output.append(line)

        return output

    @staticmethod
    def _chart_placeholder(target_language: str | None) -> str:
        return CHART_PLACEHOLDERS.get(target_language or "", CHART_PLACEHOLDERS["english"])

    @staticmethod
    def _is_probable_chart_support_line(line: str) -> bool:
        if CHART_SOURCE_PATTERN.match(line):
            return True
        if line[-1:] in ".。!?！？":
            return False
        if len(line) <= 24:
            return True
        return len(line) <= 40 and bool(CHART_SHORT_LABEL_PATTERN.fullmatch(line))
