import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.services.ocr import OcrLine, PaddleOcrProvider
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
    assert pipeline.calls == 8


def test_paddle_ocr_skips_auxiliary_passes_when_top_layout_looks_complete(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (800, 1000), "white").save(image_path)

    class FakePipeline:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def predict(self, path: str) -> list[dict[str, object]]:
            assert Path(path).is_file()
            self.calls.append(Path(path).name)
            return [
                {
                    "rec_texts": [
                        "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人",
                        "慌了手腳，急忙賣出止損。金價於是從5600美元高點回",
                        "落約10%，白銀更誇張，一周內跌逾30%，從121美元瀉",
                    ],
                    "rec_scores": [0.97, 0.98, 0.93],
                    "rec_boxes": [
                        [140, 110, 760, 140],
                        [140, 160, 760, 190],
                        [140, 210, 760, 240],
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
        "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人",
        "慌了手腳，急忙賣出止損。金價於是從5600美元高點回",
        "落約10%，白銀更誇張，一周內跌逾30%，從121美元瀉",
    ]
    assert pipeline.calls == ["page.png"]


def test_paddle_ocr_recovers_missing_first_body_line_from_enhanced_top_body_slice(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (800, 1000), "white").save(image_path)

    class FakePipeline:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def predict(self, path: str) -> list[dict[str, object]]:
            assert Path(path).is_file()
            self.calls.append(Path(path).name)
            if Path(path).name == "page.png":
                return [
                    {
                        "rec_texts": [
                            "大戶思維期權獵金",
                            "付一小筆比買股票便宜得多的期權金，就獲得在未來某個",
                        ],
                        "rec_scores": [0.88, 0.96],
                        "rec_boxes": [[0, 120, 300, 140], [0, 420, 760, 450]],
                    }
                ]
            if Path(path).name == "ocr-top-slice.png":
                return [
                    {
                        "rec_texts": ["大戶思維期權獵金"],
                        "rec_scores": [0.88],
                        "rec_boxes": [[0, 240, 600, 280]],
                    }
                ]
            if Path(path).name != "ocr-first-body-line-band-2.png":
                return []
            return [
                {
                    "rec_texts": [
                        "Option）。認購期權就像買一張「未來買入券」，只需支",
                    ],
                    "rec_scores": [0.93],
                    "rec_boxes": [[0, 801, 2100, 840]],
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
        "大戶思維期權獵金",
        "Option）。認購期權就像買一張「未來買入券」，只需支",
        "付一小筆比買股票便宜得多的期權金，就獲得在未來某個",
    ]
    assert pipeline.calls == [
        "page.png",
        "ocr-top-slice.png",
        "ocr-top-body-slice.png",
        "ocr-first-body-line-band-1.png",
        "ocr-first-body-line-band-2.png",
        "ocr-first-body-line-band-3.png",
        "ocr-first-body-line-band-4.png",
        "ocr-first-body-line-band-5.png",
    ]


def test_paddle_ocr_does_not_prepend_auxiliary_noise_mark(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (800, 1000), "white").save(image_path)

    class FakePipeline:
        def predict(self, path: str) -> list[dict[str, object]]:
            assert Path(path).is_file()
            filename = Path(path).name
            if filename == "page.png":
                return [
                    {
                        "rec_texts": ["下來。很多只買實體黃金、黃金期貨和黃金相關股票的人"],
                        "rec_scores": [0.96],
                        "rec_boxes": [[0, 320, 760, 350]],
                    }
                ]
            if filename == "ocr-first-body-line-band-1.png":
                return [
                    {
                        "rec_texts": ["-"],
                        "rec_scores": [0.76],
                        "rec_boxes": [[0, 990, 30, 1020]],
                    }
                ]
            return []

    provider = PaddleOcrProvider(
        text_detection_model="test-det",
        text_recognition_model="test-rec",
        max_image_side=1024,
        cache_path=tmp_path / "cache",
    )
    provider._pipeline = FakePipeline()

    result = provider.read_page(image_path)

    assert result.text == "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人"


def test_paddle_ocr_keeps_better_recovered_line_when_auxiliary_lines_overlap() -> None:
    full_lines = [
        OcrLine(
            text="慌了手腳，急忙賣出止損。金價於是從5600美元高點回",
            confidence=0.97,
            y_min=302,
            x_min=156,
            x_max=960,
        )
    ]
    top_lines = [
        OcrLine(
            text="下來。很多只買實體董金、董金期貨和董全相朗股西",
            confidence=0.81,
            y_min=262,
            x_min=163,
            x_max=907,
        ),
        OcrLine(
            text="下來。很多只買實體黃金、黃金期貨和黃金相關股票的人",
            confidence=0.97,
            y_min=248,
            x_min=153,
            x_max=961,
        ),
    ]

    merged = PaddleOcrProvider._merge_top_slice_lines(top_lines, full_lines)

    assert [line.text for line in merged] == [
        "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人",
        "慌了手腳，急忙賣出止損。金價於是從5600美元高點回",
    ]


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
            filename = Path(path).name
            if filename == "page.png":
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
            if filename != "ocr-top-slice.png":
                return []
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
