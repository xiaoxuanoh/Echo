from pathlib import Path

from fastapi.testclient import TestClient

from app.core.errors import EchoError
from app.services.document_processing import DocumentTextProcessingService
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.ocr import MockOcrProvider, OcrResult
from tests.conftest import make_pdf
from tests.test_uploads import image_bytes


def test_ocr_cleanup_removes_isolated_page_numbers() -> None:
    text = (
        "第一章\n"
        "資產組合裝上「安全氣囊」\n"
        "014\n"
        "Page 15\n"
        "- 16 -\n"
        "第 17 頁"
    )

    cleaned = DocumentTextProcessingService._remove_isolated_page_number_lines(text)

    assert cleaned == "第一章\n資產組合裝上「安全氣囊」"


def test_ocr_cleanup_preserves_inline_numbers() -> None:
    text = (
        "這本書就是要告訴你：不！現金存款、住宅物業、債券、014\n"
        "第14章\n"
        "2026年市場情況"
    )

    cleaned = DocumentTextProcessingService._remove_isolated_page_number_lines(text)

    assert cleaned == text


def test_ocr_cleanup_removes_running_header() -> None:
    text = (
        "第一章 大戶候機隨勢變招\n"
        "圖1.1：SPDR 黃金 ETF (GLD) 股價走勢\n"
        "資料來源：Nasdaq.com\n"
        "槓效應有限風險。你的核心股票投資組合，負責穩穩增值。"
    )

    cleaned = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="cantonese",
    )

    assert cleaned == (
        "此處有一個圖表。\n"
        "槓效應有限風險。你的核心股票投資組合，負責穩穩增值。"
    )


def test_ocr_cleanup_uses_target_language_for_chart_placeholder() -> None:
    text = (
        "Figure 1.1: SPDR Gold ETF price trend\n"
        "USD\n"
        "Source: Nasdaq.com\n"
        "The market does not only move upward."
    )

    mandarin = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="mandarin",
    )
    english = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="english",
    )
    fallback = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language=None,
    )

    assert mandarin == "此处有一个图表。\nThe market does not only move upward."
    assert english == "There is a chart here.\nThe market does not only move upward."
    assert fallback == "There is a chart here.\nThe market does not only move upward."


def test_processes_all_image_pages_in_order(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/images",
        files=[
            ("files", ("first.png", image_bytes((20, 30)), "image/png")),
            ("files", ("second.png", image_bytes((20, 30)), "image/png")),
        ],
        data={"rotations": "[0, 0]"},
    ).json()

    accepted = client.post(f"/api/books/{upload['book_id']}/process-text")
    detail = client.get(f"/api/books/{upload['book_id']}")

    assert accepted.status_code == 202
    assert accepted.json()["processing_status"] == "running_ocr"
    assert detail.status_code == 200
    result = detail.json()
    assert result["processing_status"] == "text_ready"
    assert result["completed_pages"] == 2
    assert result["failed_pages"] == 0
    assert result["processing_active"] is False
    assert [page["page_number"] for page in result["pages"]] == [1, 2]
    assert all(
        page["extracted_text"] == "這是本地測試文字。" for page in result["pages"]
    )

    saved = LocalDocumentMetadataService().load(storage_path / upload["book_id"])
    assert saved.status == "text_ready"
    assert all(page.processing_status == "completed" for page in saved.pages)


def test_mixed_pdf_preserves_embedded_text_and_reads_scanned_page(
    client: TestClient,
) -> None:
    embedded_text = "This embedded page text must be preserved exactly."
    upload = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "mixed.pdf",
                make_pdf([embedded_text, None]),
                "application/pdf",
            )
        },
    ).json()

    response = client.post(f"/api/books/{upload['book_id']}/process-text")
    detail = client.get(f"/api/books/{upload['book_id']}").json()

    assert response.status_code == 202
    assert detail["processing_status"] == "text_ready"
    assert detail["pages"][0]["extraction_method"] == "embedded_text"
    assert detail["pages"][0]["extracted_text"] == embedded_text
    assert detail["pages"][1]["extraction_method"] == "ocr"
    assert detail["pages"][1]["extracted_text"] == "這是本地測試文字。"


def test_retries_only_a_failed_page(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_directory = storage_path / upload["book_id"]
    metadata = LocalDocumentMetadataService()
    document = metadata.load(document_directory)
    document.status = "failed"
    document.error_message = "1 page still needs attention."
    document.pages[0].processing_status = "failed"
    document.pages[0].error_message = "Echo could not read the text on this page."
    metadata.save(document_directory, document)

    accepted = client.post(f"/api/books/{upload['book_id']}/pages/1/retry-text")
    detail = client.get(f"/api/books/{upload['book_id']}").json()

    assert accepted.status_code == 202
    assert detail["processing_status"] == "text_ready"
    assert detail["pages"][0]["processing_status"] == "completed"
    assert detail["pages"][0]["error_message"] is None


def test_rejects_retry_for_a_page_that_has_not_failed(client: TestClient) -> None:
    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()

    response = client.post(f"/api/books/{upload['book_id']}/pages/1/retry-text")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "page_not_failed"


def test_saves_failure_then_successfully_retries(
    client: TestClient,
    storage_path: Path,
) -> None:
    class FailingProvider:
        def read_page(self, _: Path) -> OcrResult:
            raise EchoError("test_failure", "This page needs another try.")

    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_id = LocalDocumentMetadataService().load(storage_path / upload["book_id"]).id
    failing_service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=FailingProvider(),
    )

    failing_service.prepare_document_job(document_id)
    failing_service.process_document(document_id)
    failed = failing_service.load_document(document_id)

    assert failed.status == "failed"
    assert failed.pages[0].processing_status == "failed"
    assert failed.pages[0].error_message == "This page needs another try."

    retry_service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=MockOcrProvider(),
    )
    retry_service.prepare_retry_job(document_id, 1)
    retry_service.retry_page(document_id, 1)
    completed = retry_service.load_document(document_id)

    assert completed.status == "text_ready"
    assert completed.pages[0].processing_status == "completed"


def test_embedded_text_finishes_when_ocr_is_disabled(
    client: TestClient,
) -> None:
    client.app.state.settings.use_mock_ocr = False
    client.app.state.settings.ocr_enabled = False
    embedded_text = "This digital page does not need an OCR provider."
    upload = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "digital.pdf",
                make_pdf([embedded_text]),
                "application/pdf",
            )
        },
    ).json()

    response = client.post(f"/api/books/{upload['book_id']}/process-text")
    detail = client.get(f"/api/books/{upload['book_id']}").json()

    assert response.status_code == 202
    assert detail["processing_status"] == "text_ready"
    assert detail["pages"][0]["extracted_text"] == embedded_text
