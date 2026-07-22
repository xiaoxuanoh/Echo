from pathlib import Path

from fastapi.testclient import TestClient

from app.core.errors import EchoError
from app.services.book_processing import BookTextProcessingService
from app.services.book_metadata import LocalBookMetadataService
from app.services.ocr import MockOcrProvider, OcrResult
from tests.conftest import make_pdf
from tests.test_uploads import image_bytes


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

    saved = LocalBookMetadataService().load(storage_path / upload["book_id"])
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
    book_directory = storage_path / upload["book_id"]
    metadata = LocalBookMetadataService()
    book = metadata.load(book_directory)
    book.status = "failed"
    book.error_message = "1 page still needs attention."
    book.pages[0].processing_status = "failed"
    book.pages[0].error_message = "Echo could not read the text on this page."
    metadata.save(book_directory, book)

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
    book_id = LocalBookMetadataService().load(storage_path / upload["book_id"]).id
    failing_service = BookTextProcessingService(
        storage_root=storage_path,
        ocr_provider=FailingProvider(),
    )

    failing_service.prepare_book_job(book_id)
    failing_service.process_book(book_id)
    failed = failing_service.load_book(book_id)

    assert failed.status == "failed"
    assert failed.pages[0].processing_status == "failed"
    assert failed.pages[0].error_message == "This page needs another try."

    retry_service = BookTextProcessingService(
        storage_root=storage_path,
        ocr_provider=MockOcrProvider(),
    )
    retry_service.prepare_retry_job(book_id, 1)
    retry_service.retry_page(book_id, 1)
    completed = retry_service.load_book(book_id)

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
