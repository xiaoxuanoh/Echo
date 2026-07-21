from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pypdfium2 as pdfium
from PIL import Image

from app.core.errors import EchoError


PageKind = Literal["embedded_text", "requires_ocr"]
DocumentKind = Literal["text", "scanned", "mixed"]


@dataclass(frozen=True)
class PageInspection:
    page_number: int
    classification: PageKind
    extracted_character_count: int


@dataclass(frozen=True)
class PdfInspection:
    total_pages: int
    classification: DocumentKind
    pages: list[PageInspection]


class PdfProcessingService:
    """Keeps every pypdfium2 call behind one replaceable service boundary."""

    def __init__(self, text_min_characters: int) -> None:
        self.text_min_characters = text_min_characters

    def validate_pdf(self, path: Path) -> None:
        with path.open("rb") as pdf_file:
            header = pdf_file.read(1024)
        if b"%PDF-" not in header:
            raise EchoError("invalid_pdf", "The selected file is not a valid PDF.")

        document = self._open_document(path)
        try:
            if len(document) == 0:
                raise EchoError("empty_pdf", "The PDF does not contain any pages.")
        finally:
            document.close()

    def count_pages(self, path: Path) -> int:
        document = self._open_document(path)
        try:
            return len(document)
        finally:
            document.close()

    def extract_page_text(self, path: Path, page_index: int) -> str:
        document = self._open_document(path)
        try:
            return self._extract_text(document, page_index)
        finally:
            document.close()

    def render_page(
        self,
        path: Path,
        page_index: int,
        *,
        scale: float = 2.0,
    ) -> Image.Image:
        document = self._open_document(path)
        try:
            page = document[page_index]
            try:
                bitmap = page.render(scale=scale)
                try:
                    return bitmap.to_pil().copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()

    def classify_pdf(self, path: Path) -> PdfInspection:
        self.validate_pdf(path)
        document = self._open_document(path)
        try:
            pages: list[PageInspection] = []
            for page_index in range(len(document)):
                text = self._extract_text(document, page_index)
                character_count = sum(not character.isspace() for character in text)
                classification: PageKind = (
                    "embedded_text"
                    if character_count >= self.text_min_characters
                    else "requires_ocr"
                )
                pages.append(
                    PageInspection(
                        page_number=page_index + 1,
                        classification=classification,
                        extracted_character_count=character_count,
                    )
                )

            page_kinds = {page.classification for page in pages}
            if page_kinds == {"embedded_text"}:
                document_kind: DocumentKind = "text"
            elif page_kinds == {"requires_ocr"}:
                document_kind = "scanned"
            else:
                document_kind = "mixed"

            return PdfInspection(
                total_pages=len(document),
                classification=document_kind,
                pages=pages,
            )
        finally:
            document.close()

    def _open_document(self, path: Path) -> pdfium.PdfDocument:
        try:
            return pdfium.PdfDocument(path)
        except Exception as error:
            raise EchoError(
                "invalid_pdf",
                "The PDF could not be opened. It may be damaged or password protected.",
            ) from error

    @staticmethod
    def _extract_text(document: pdfium.PdfDocument, page_index: int) -> str:
        try:
            page = document[page_index]
            try:
                text_page = page.get_textpage()
                try:
                    return text_page.get_text_bounded()
                finally:
                    text_page.close()
            finally:
                page.close()
        except IndexError as error:
            raise EchoError("invalid_page", "The requested PDF page does not exist.") from error
        except EchoError:
            raise
        except Exception as error:
            raise EchoError(
                "pdf_text_error",
                "Echo could not inspect the text on one of the PDF pages.",
            ) from error
