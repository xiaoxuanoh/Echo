import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.ocr import PaddleOcrProvider
from tests.test_uploads import image_bytes


def upload_one_page(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((30, 40)), "image/png"))],
        data={"rotations": "[0]"},
    )
    assert response.status_code == 200
    return response.json()


def test_previews_one_page_with_mock_provider(client: TestClient) -> None:
    uploaded = upload_one_page(client)

    response = client.post(f"/api/books/{uploaded['book_id']}/pages/1/text-preview")

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "mock"
    assert result["text"] == "這是本地測試文字。"
    assert result["average_confidence"] == 1.0
    assert result["persisted"] is False


def test_preview_does_not_change_book_metadata(
    client: TestClient,
    storage_path: Path,
) -> None:
    uploaded = upload_one_page(client)
    metadata_path = storage_path / str(uploaded["book_id"]) / "book.json"
    before = json.loads(metadata_path.read_text(encoding="utf-8"))

    response = client.post(f"/api/books/{uploaded['book_id']}/pages/1/text-preview")

    assert response.status_code == 200
    after = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert after == before
    assert after["pages"][0]["extracted_text"] == ""


def test_rejects_unknown_book_and_page(client: TestClient) -> None:
    unknown_book = client.post(
        "/api/books/00000000-0000-0000-0000-000000000000/pages/1/text-preview"
    )
    uploaded = upload_one_page(client)
    unknown_page = client.post(f"/api/books/{uploaded['book_id']}/pages/2/text-preview")

    assert unknown_book.status_code == 404
    assert unknown_book.json()["error"]["code"] == "book_not_found"
    assert unknown_page.status_code == 404
    assert unknown_page.json()["error"]["code"] == "page_not_found"


def test_converts_paddle_prediction_to_lines() -> None:
    lines = PaddleOcrProvider._lines_from_prediction(
        {
            "rec_texts": [" 第一行 ", "", "第二行"],
            "rec_scores": [0.91, 0.3, 1.2],
        }
    )

    assert [line.text for line in lines] == ["第一行", "第二行"]
    assert [line.confidence for line in lines] == pytest.approx([0.91, 1.0])
