import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from threading import Lock
from uuid import UUID

from app.core.errors import EchoError
from app.models.documents import DocumentPageRecord, DocumentRecord
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.ocr import OcrLine, OcrProvider


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
    r"^(?:資料來源|資料来源|资料來源|资料来源|來源|来源|source)\s*[:：]?.*",
    re.IGNORECASE,
)
CHART_SHORT_LABEL_PATTERN = re.compile(
    r"^[\w\s().,%/+-]*$",
    re.IGNORECASE,
)
CJK_CHARACTER_PATTERN = re.compile(r"[\u3400-\u9fff]")
CJK_PROSE_PUNCTUATION_PATTERN = re.compile(r"[，。！？；：「」『』]")
LATIN_CHARACTER_PATTERN = re.compile(r"[A-Za-z]")
MEANINGFUL_CJK_PROSE_MINIMUM = 8
LOW_CONFIDENCE_NOISE_THRESHOLD = 0.50
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
        ensure_page_file: Callable[
            [DocumentRecord, DocumentPageRecord, Path],
            None,
        ]
        | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.ocr_provider = ocr_provider
        self.metadata = metadata or LocalDocumentMetadataService()
        self.ensure_page_file = ensure_page_file

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

    def update_page_text(
        self,
        document_id: UUID,
        page_number: int,
        text: str,
    ) -> DocumentRecord:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise EchoError(
                "page_text_required",
                "Enter the page text before saving.",
                status_code=422,
            )
        document = self.load_document(document_id)
        page = self._find_page(document, page_number)
        now = datetime.now(UTC)
        page.extracted_text = cleaned_text
        page.processing_status = "completed"
        page.error_message = None
        page.updated_at = now
        document.error_message = None
        document.audio_segments = []
        document.status = (
            "text_ready"
            if all(candidate.processing_status == "completed" for candidate in document.pages)
            else "failed"
        )
        if document.status == "failed":
            failed_pages = [
                candidate
                for candidate in document.pages
                if candidate.processing_status == "failed"
            ]
            document.error_message = (
                f"{len(failed_pages)} page"
                f"{'s' if len(failed_pages) != 1 else ''} still need attention."
            )
        document.updated_at = now
        self.metadata.save(self.document_directory(document.id), document)
        return document

    def mark_text_job_failed(
        self,
        document_id: UUID,
        message: str = "Page text preparation stopped before it finished.",
    ) -> None:
        document = self.load_document(document_id)
        now = datetime.now(UTC)
        for page in document.pages:
            if page.processing_status in {"pending", "running_ocr", "extracting"}:
                page.processing_status = "failed"
                page.error_message = message
                page.updated_at = now
        document.status = "failed"
        document.error_message = message
        document.updated_at = now
        self.metadata.save(self.document_directory(document.id), document)

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
            if self.ensure_page_file is not None:
                self.ensure_page_file(document, page, image_path)
            result = self.ocr_provider.read_page(image_path)
            if not result.text.strip():
                raise EchoError(
                    "no_page_text",
                    "Echo could not find readable text on this page.",
                )
            page.extracted_text = self._clean_ocr_result(
                result.lines,
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
        lines = cls._prepare_ocr_text_lines(text)
        cleaned_lines = cls._replace_chart_blocks(lines, target_language=target_language)
        return "\n".join(line for line in cleaned_lines if line.strip()).strip()

    @classmethod
    def _clean_ocr_result(
        cls,
        lines: list[OcrLine],
        *,
        target_language: str | None,
    ) -> str:
        text_lines = cls._prepare_ocr_lines(lines)
        cleaned_lines = cls._replace_chart_blocks(
            text_lines,
            target_language=target_language,
        )
        cleaned_lines = cls._remove_short_orphan_lines(cleaned_lines)
        return "\n".join(line for line in cleaned_lines if line.strip()).strip()

    @classmethod
    def _prepare_ocr_text_lines(cls, text: str) -> list[str]:
        return cls._remove_running_headers(
            cls._remove_isolated_page_number_lines(text).splitlines()
        )

    @classmethod
    def _prepare_ocr_lines(cls, lines: list[OcrLine]) -> list[str]:
        kept_lines = [
            line.text
            for line in lines
            if cls._should_keep_confident_line(line)
        ]
        return cls._remove_running_headers(
            cls._remove_isolated_page_number_lines("\n".join(kept_lines)).splitlines()
        )

    @staticmethod
    def _should_keep_confident_line(line: OcrLine) -> bool:
        text = line.text.strip()
        if not text:
            return False
        if (
            line.confidence < LOW_CONFIDENCE_NOISE_THRESHOLD
            and len(text) <= 12
            and not CJK_PROSE_PUNCTUATION_PATTERN.search(text)
        ):
            return False
        return True

    @staticmethod
    def _remove_running_headers(lines: list[str]) -> list[str]:
        cleaned = list(lines)
        for index, line in enumerate(cleaned):
            if index >= 4 and index != len(cleaned) - 1:
                continue
            if RUNNING_HEADER_PATTERN.fullmatch(
                line.strip(),
            ) or DocumentTextProcessingService._is_top_running_title(
                line.strip(),
                index=index,
                lines=cleaned,
            ):
                cleaned[index] = ""
        return [line for line in cleaned if line.strip()]

    @staticmethod
    def _is_top_running_title(line: str, *, index: int, lines: list[str]) -> bool:
        if index > 1:
            return False
        if len(line) > 16 or CJK_PROSE_PUNCTUATION_PATTERN.search(line):
            return False
        cjk_count = len(CJK_CHARACTER_PATTERN.findall(line))
        if cjk_count < 4:
            return False

        following_lines = [candidate.strip() for candidate in lines[index + 1 : index + 4]]
        return any(
            len(CJK_CHARACTER_PATTERN.findall(candidate)) >= MEANINGFUL_CJK_PROSE_MINIMUM
            and CJK_PROSE_PUNCTUATION_PATTERN.search(candidate)
            for candidate in following_lines
        )

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
        cjk_count = len(CJK_CHARACTER_PATTERN.findall(line))
        if (
            cjk_count == 0
            and len(line) <= 24
            and bool(CHART_SHORT_LABEL_PATTERN.fullmatch(line))
        ):
            return True
        if line[-1:] in ".。!?！？":
            return False
        if CJK_PROSE_PUNCTUATION_PATTERN.search(line):
            return False
        if cjk_count >= MEANINGFUL_CJK_PROSE_MINIMUM:
            return False
        if len(line) <= 24:
            return True
        return len(line) <= 40 and bool(CHART_SHORT_LABEL_PATTERN.fullmatch(line))

    @classmethod
    def _remove_short_orphan_lines(cls, lines: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if cls._is_short_orphan_line(stripped, index=index, total=len(lines)):
                continue
            cleaned.append(line)
        return cleaned

    @staticmethod
    def _is_short_orphan_line(line: str, *, index: int, total: int) -> bool:
        cjk_count = len(CJK_CHARACTER_PATTERN.findall(line))
        has_latin = bool(LATIN_CHARACTER_PATTERN.search(line))
        has_prose_punctuation = bool(CJK_PROSE_PUNCTUATION_PATTERN.search(line))
        if index <= 2 and has_latin and len(line) <= 12 and cjk_count == 0:
            return True
        if index <= 3 and 0 < cjk_count <= 1 and not has_prose_punctuation:
            return True
        if (
            0 < cjk_count < MEANINGFUL_CJK_PROSE_MINIMUM
            and not has_prose_punctuation
            and 0 < index < total - 1
        ):
            return True
        return False
