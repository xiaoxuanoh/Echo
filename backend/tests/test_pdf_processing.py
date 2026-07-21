from pathlib import Path

import pytest

from app.core.errors import EchoError
from app.services.pdf_processing import PdfProcessingService
from tests.conftest import make_pdf


@pytest.mark.parametrize(
    ("page_texts", "expected"),
    [
        (["A full page of selectable embedded text."], "text"),
        ([None], "scanned"),
        (["A full page of selectable embedded text.", None], "mixed"),
    ],
)
def test_classifies_all_pdf_pages(
    tmp_path: Path,
    page_texts: list[str | None],
    expected: str,
) -> None:
    path = tmp_path / "book.pdf"
    path.write_bytes(make_pdf(page_texts))
    service = PdfProcessingService(text_min_characters=20)

    result = service.classify_pdf(path)

    assert result.classification == expected
    assert result.total_pages == len(page_texts)
    assert [page.page_number for page in result.pages] == list(
        range(1, len(page_texts) + 1)
    )


def test_extracts_embedded_text_and_renders_page(tmp_path: Path) -> None:
    path = tmp_path / "book.pdf"
    path.write_bytes(make_pdf(["Traditional Chinese digital book text."]))
    service = PdfProcessingService(text_min_characters=20)

    text = service.extract_page_text(path, 0)
    image = service.render_page(path, 0)

    assert "digital book text" in text
    assert image.width > 0
    assert image.height > 0


def test_rejects_non_pdf_content(tmp_path: Path) -> None:
    path = tmp_path / "not-a-pdf.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(EchoError, match="not a valid PDF"):
        PdfProcessingService(text_min_characters=20).validate_pdf(path)
