import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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


def test_preview_does_not_change_document_metadata(
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
            "rec_boxes": [[0, 10, 100, 20], [0, 30, 100, 40], [0, 50, 100, 60]],
        }
    )

    assert [line.text for line in lines] == ["第一行", "第二行"]
    assert [line.confidence for line in lines] == pytest.approx([0.91, 1.0])
    assert [line.y_min for line in lines] == pytest.approx([10, 50])


def test_converts_paddle_numpy_boxes_without_truth_check_error() -> None:
    class AmbiguousBoxes:
        def __bool__(self) -> bool:
            raise ValueError("ambiguous truth value")

        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> list[int]:
            assert index == 0
            return [0, 10, 100, 20]

    lines = PaddleOcrProvider._lines_from_prediction(
        {
            "rec_texts": ["第一行"],
            "rec_scores": [0.91],
            "rec_boxes": AmbiguousBoxes(),
        }
    )

    assert lines[0].text == "第一行"
    assert lines[0].y_min == pytest.approx(10)


def test_paddle_ocr_prepends_unique_lines_from_top_slice(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (240, 320), "white").save(image_path)

    class FakePipeline:
        def __init__(self) -> None:
            self.calls = 0

        def predict(self, path: str) -> list[dict[str, object]]:
            assert Path(path).is_file()
            self.calls += 1
            if self.calls == 1:
                return [
                    {
                        "rec_texts": ["工具，也是大戶投資者的日常工具。"],
                        "rec_scores": [0.95],
                        "rec_boxes": [[0, 110, 200, 130]],
                    }
                ]
            return [
                {
                    "rec_texts": [
                        "讀畢本章，當你知道如何謹慎且適當地使用時",
                        "期權不一定是賭博，它也可以是一個非常重要的風險管理",
                        "工具，也是大戶投資者的日常工具。",
                    ],
                    "rec_scores": [0.94, 0.93, 0.95],
                    "rec_boxes": [
                        [0, 120, 400, 140],
                        [0, 160, 400, 180],
                        [0, 220, 400, 240],
                    ],
                }
            ]

    provider = PaddleOcrProvider(
        text_detection_model="test-det",
        text_recognition_model="test-rec",
        max_image_side=1024,
        cache_path=tmp_path / "cache",
    )
    pipeline = FakePipeline()
    provider._pipeline = pipeline

    result = provider.read_page(image_path)

    assert result.text.splitlines() == [
        "讀畢本章，當你知道如何謹慎且適當地使用時",
        "期權不一定是賭博，它也可以是一個非常重要的風險管理",
        "工具，也是大戶投資者的日常工具。",
    ]
    assert pipeline.calls == 2


def test_paddle_ocr_does_not_prepend_misordered_lower_top_slice_line(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (240, 320), "white").save(image_path)

    class FakePipeline:
        def __init__(self) -> None:
            self.calls = 0

        def predict(self, path: str) -> list[dict[str, object]]:
            assert Path(path).is_file()
            self.calls += 1
            if self.calls == 1:
                return [
                    {
                        "rec_texts": [
                            "期權不一定是賭博，它也可以是一個非常重要的風險管理",
                            "多，有些是純粹的投機者，有些是長期投資者，也有股票",
                        ],
                        "rec_scores": [0.94, 0.95],
                        "rec_boxes": [[0, 120, 400, 140], [0, 180, 400, 200]],
                    }
                ]
            return [
                {
                    "rec_texts": [
                        "松明白期權如何在現實中發揮神奇作用",
                        "期權不一定是賭博，它也可以是一個非常重要的風險管理",
                    ],
                    "rec_scores": [0.91, 0.94],
                    "rec_boxes": [
                        [0, 500, 800, 540],
                        [0, 260, 800, 300],
                    ],
                }
            ]

    provider = PaddleOcrProvider(
        text_detection_model="test-det",
        text_recognition_model="test-rec",
        max_image_side=1024,
        cache_path=tmp_path / "cache",
    )
    provider._pipeline = FakePipeline()

    result = provider.read_page(image_path)

    assert result.text.splitlines() == [
        "期權不一定是賭博，它也可以是一個非常重要的風險管理",
        "多，有些是純粹的投機者，有些是長期投資者，也有股票",
    ]
