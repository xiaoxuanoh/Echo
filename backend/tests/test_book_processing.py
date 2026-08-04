from pathlib import Path

from fastapi.testclient import TestClient

from app.core.errors import EchoError
from app.services.document_processing import DocumentTextProcessingService
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.ocr import MockOcrProvider, OcrLine, OcrResult
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


def test_ocr_cleanup_removes_short_top_running_title() -> None:
    text = (
        "大户思维期權獵金\n"
        "多，有些是純粹的投機者，有些是長期投資者，也有股票\n"
        "經紀和交易商，有些代表退休基金客戶或像你我這樣的普通散戶投資者。\n"
    )

    cleaned = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="cantonese",
    )

    assert cleaned == (
        "多，有些是純粹的投機者，有些是長期投資者，也有股票\n"
        "經紀和交易商，有些代表退休基金客戶或像你我這樣的普通散戶投資者。"
    )


def test_ocr_cleanup_preserves_body_heading_after_prose() -> None:
    text = (
        "現在，讓我們看看3個最近發生的市場故事。\n"
        "故事一：期權魔法，用小錢抓住「黃金」機會\n"
        "你每天上班下班，偶爾看新聞時發現黃金價格直衝雲霄。"
    )

    cleaned = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="cantonese",
    )

    assert cleaned == text


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


def test_ocr_cleanup_removes_chart_axis_noise_with_period() -> None:
    text = (
        "圖1.2：SLV白銀ETF股價走勢\n"
        "美元\n"
        "90\n"
        "70\n"
        "50\n"
        "成交量（萬股）\n"
        "40000\n"
        "-20000\n"
        "latwalth.\n"
        "5/2025\n"
        "1/2026\n"
        "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人"
    )

    cleaned = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="cantonese",
    )

    assert cleaned == (
        "此處有一個圖表。\n"
        "下來。很多只買實體黃金、黃金期貨和黃金相關股票的人"
    )


def test_ocr_cleanup_preserves_cjk_prose_after_chart_source() -> None:
    text = (
        "圖1.1：SPDR黄金ETF（GLD）股價走勢\n"
        "美元\n"
        "450\n"
        "400\n"
        "350\n"
        "300\n"
        "成交量（萬股）\n"
        "5000\n"
        "1/2026\n"
        "11\n"
        "3\n"
        "5/2025\n"
        "7\n"
        "资料來源：Nasdaq.com\n"
        "桿效應+有限風險。你的核心股票投資組合，負責穩穩\n"
        "增值，例如長期持有礦業股或ETF·期權則像「火箭推進"
    )

    cleaned = DocumentTextProcessingService._clean_ocr_text(
        text,
        target_language="cantonese",
    )

    assert cleaned == (
        "此處有一個圖表。\n"
        "桿效應+有限風險。你的核心股票投資組合，負責穩穩\n"
        "增值，例如長期持有礦業股或ETF·期權則像「火箭推進"
    )


def test_ocr_result_cleanup_removes_noise_around_chart_and_body() -> None:
    lines = [
        OcrLine(text="ae", confidence=0.23),
        OcrLine(text="hiwlo", confidence=0.36),
        OcrLine(text="第一章大户候機随勢變招", confidence=0.90),
        OcrLine(text="支", confidence=1.0),
        OcrLine(text="圖1.1：SPDR黄金ETF（GLD）股價走勢", confidence=0.94),
        OcrLine(text="個", confidence=0.99),
        OcrLine(text="美元", confidence=1.0),
        OcrLine(text="權", confidence=0.94),
        OcrLine(text="450", confidence=0.98),
        OcrLine(text="Narita", confidence=1.0),
        OcrLine(text="成交量（萬股）", confidence=0.96),
        OcrLine(text="·5000", confidence=0.86),
        OcrLine(text="资料來源：Nasdaq.com", confidence=0.93),
        OcrLine(
            text="桿效應+有限風險。你的核心股票投資組合，負責穩穩",
            confidence=0.98,
        ),
        OcrLine(
            text="增值，例如長期持有礦業股或ETF·期權則像「火箭推進",
            confidence=0.97,
        ),
        OcrLine(
            text="器」，讓你在行情來臨時用小錢賺大錢。只用積蓄的一小",
            confidence=0.98,
        ),
        OcrLine(text="覺也安心！", confidence=0.99),
        OcrLine(text="是投輕横", confidence=0.88),
        OcrLine(
            text="可是，市場從來不會只升不跌。2026年1月底，金價和銀",
            confidence=0.99,
        ),
    ]

    cleaned = DocumentTextProcessingService._clean_ocr_result(
        lines,
        target_language="cantonese",
    )

    assert cleaned == (
        "此處有一個圖表。\n"
        "桿效應+有限風險。你的核心股票投資組合，負責穩穩\n"
        "增值，例如長期持有礦業股或ETF·期權則像「火箭推進\n"
        "器」，讓你在行情來臨時用小錢賺大錢。只用積蓄的一小\n"
        "覺也安心！\n"
        "可是，市場從來不會只升不跌。2026年1月底，金價和銀"
    )


def test_ocr_result_cleanup_collapses_figure_layout_text_before_body() -> None:
    lines = [
        OcrLine(
            text="圖1.3：白銀 ETF 期權合約價格起跌",
            confidence=0.95,
            y_min=80,
            x_min=160,
            x_max=620,
        ),
        OcrLine(
            text="目標是每日投資收益相當於彭博白銀指數單",
            confidence=0.91,
            y_min=300,
            x_min=390,
            x_max=700,
        ),
        OcrLine(
            text="2月27日到期、行使價75美元的買權",
            confidence=0.93,
            y_min=330,
            x_min=110,
            x_max=350,
        ),
        OcrLine(
            text="日表現的兩倍反向（-2X)",
            confidence=0.90,
            y_min=360,
            x_min=390,
            x_max=620,
        ),
        OcrLine(
            text="3月20日到期、行使價3美元的買權",
            confidence=0.93,
            y_min=390,
            x_min=390,
            x_max=650,
        ),
        OcrLine(
            text="白銀價格從2025年初每盎斯30美元上漲至2026年1月的每盎斯115美元，這",
            confidence=0.98,
            y_min=510,
            x_min=90,
            x_max=760,
        ),
        OcrLine(
            text="一短期且幅度巨大的上漲吸引了更多投機性甚至錯失恐懼症（Fear of Missing",
            confidence=0.97,
            y_min=545,
            x_min=90,
            x_max=780,
        ),
    ]

    cleaned = DocumentTextProcessingService._clean_ocr_result(
        lines,
        target_language="cantonese",
    )

    assert cleaned == (
        "此處有一個圖表。\n"
        "白銀價格從2025年初每盎斯30美元上漲至2026年1月的每盎斯115美元，這\n"
        "一短期且幅度巨大的上漲吸引了更多投機性甚至錯失恐懼症（Fear of Missing"
    )


def test_ocr_result_cleanup_preserves_short_body_lines_without_chart_context() -> None:
    lines = [
        OcrLine(
            text="低目標價位的股票，組合起來既達到穩守突擊效果，降低",
            confidence=0.98,
            y_min=620,
            x_min=90,
            x_max=760,
        ),
        OcrLine(
            text="對短期極端波動的影響，甚至增加長期回報和跑贏大市的",
            confidence=0.98,
            y_min=660,
            x_min=90,
            x_max=760,
        ),
        OcrLine(
            text="潛在機會。",
            confidence=0.99,
            y_min=700,
            x_min=90,
            x_max=240,
        ),
    ]

    cleaned = DocumentTextProcessingService._clean_ocr_result(
        lines,
        target_language="cantonese",
    )

    assert cleaned == (
        "低目標價位的股票，組合起來既達到穩守突擊效果，降低\n"
        "對短期極端波動的影響，甚至增加長期回報和跑贏大市的\n"
        "潛在機會。"
    )


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


def test_updates_failed_page_text_manually(
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

    response = client.patch(
        f"/api/books/{upload['book_id']}/pages/1/text",
        json={"text": "讀畢本章，當你知道如何謹慎且適當地使用時。"},
    )

    assert response.status_code == 200
    detail = response.json()
    assert detail["processing_status"] == "text_ready"
    assert detail["completed_pages"] == 1
    assert detail["failed_pages"] == 0
    assert detail["pages"][0]["processing_status"] == "completed"
    assert detail["pages"][0]["error_message"] is None
    assert detail["pages"][0]["extracted_text"].startswith("讀畢本章")


def test_uncertain_ocr_page_requires_manual_review(
    client: TestClient,
    storage_path: Path,
) -> None:
    warning = (
        "Echo found possible text near the top of this page, but it may contain "
        "OCR mistakes. Please review this page before listening."
    )

    class WarningProvider:
        def read_page(self, _: Path) -> OcrResult:
            return OcrResult(
                provider="paddleocr",
                text="甚至反向賺更多。",
                lines=[OcrLine(text="甚至反向賺更多。", confidence=0.98)],
                average_confidence=0.98,
                processing_time_seconds=0.01,
                warnings=[warning],
            )

    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_id = LocalDocumentMetadataService().load(storage_path / upload["book_id"]).id
    service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=WarningProvider(),
    )

    service.process_document(document_id)

    saved = service.load_document(document_id)
    assert saved.status == "failed"
    assert saved.pages[0].processing_status == "failed"
    assert saved.pages[0].extracted_text == "甚至反向賺更多。"
    assert saved.pages[0].error_message == warning
    assert saved.pages[0].warning_messages == []


def test_figure_only_ocr_warning_does_not_block_usable_page(
    client: TestClient,
    storage_path: Path,
) -> None:
    warning = (
        "Echo found possible text near the top of this page, but it may contain "
        "OCR mistakes. Please review this page before listening."
    )

    class FigureWarningProvider:
        def read_page(self, _: Path) -> OcrResult:
            lines = [
                OcrLine(
                    text="圖1.3：白銀 ETF 期權合約價格起跌",
                    confidence=0.95,
                    y_min=80,
                    x_min=160,
                    x_max=620,
                ),
                OcrLine(
                    text="目標是每日投資收益相當於彭博白銀指數單",
                    confidence=0.91,
                    y_min=300,
                    x_min=390,
                    x_max=700,
                ),
                OcrLine(
                    text="2月27日到期、行使價75美元的買權",
                    confidence=0.93,
                    y_min=330,
                    x_min=110,
                    x_max=350,
                ),
                OcrLine(
                    text="白銀價格從2025年初每盎斯30美元上漲至2026年1月的每盎斯115美元，這",
                    confidence=0.98,
                    y_min=510,
                    x_min=90,
                    x_max=760,
                ),
            ]
            return OcrResult(
                provider="paddleocr",
                text="\n".join(line.text for line in lines),
                lines=lines,
                average_confidence=0.95,
                processing_time_seconds=0.01,
                warnings=[warning],
            )

    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_id = LocalDocumentMetadataService().load(storage_path / upload["book_id"]).id
    service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=FigureWarningProvider(),
    )

    service.process_document(document_id)

    saved = service.load_document(document_id)
    assert saved.status == "text_ready"
    assert saved.pages[0].processing_status == "completed"
    assert saved.pages[0].error_message is None
    assert saved.pages[0].warning_messages == [
        "This page contains chart or figure text. Please review the extracted "
        "text before generating audio."
    ]
    assert saved.pages[0].extracted_text == (
        "There is a chart here.\n"
        "白銀價格從2025年初每盎斯30美元上漲至2026年1月的每盎斯115美元，這"
    )


def test_figure_page_without_ocr_warning_still_recommends_review(
    client: TestClient,
    storage_path: Path,
) -> None:
    class FigureProvider:
        def read_page(self, _: Path) -> OcrResult:
            lines = [
                OcrLine(
                    text="圖1.3：白銀 ETF 期權合約價格起跌",
                    confidence=0.95,
                    y_min=80,
                    x_min=160,
                    x_max=620,
                ),
                OcrLine(
                    text="目標是每日投資收益相當於彭博白銀指數單",
                    confidence=0.91,
                    y_min=300,
                    x_min=390,
                    x_max=700,
                ),
                OcrLine(
                    text="2月27日到期、行使價75美元的買權",
                    confidence=0.93,
                    y_min=330,
                    x_min=110,
                    x_max=350,
                ),
                OcrLine(
                    text="白銀價格從2025年初每盎斯30美元上漲至2026年1月的每盎斯115美元，這",
                    confidence=0.98,
                    y_min=510,
                    x_min=90,
                    x_max=760,
                ),
            ]
            return OcrResult(
                provider="paddleocr",
                text="\n".join(line.text for line in lines),
                lines=lines,
                average_confidence=0.95,
                processing_time_seconds=0.01,
                warnings=[],
            )

    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_id = LocalDocumentMetadataService().load(storage_path / upload["book_id"]).id
    service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=FigureProvider(),
    )

    service.process_document(document_id)

    saved = service.load_document(document_id)
    assert saved.status == "text_ready"
    assert saved.pages[0].processing_status == "completed"
    assert saved.pages[0].error_message is None
    assert saved.pages[0].warning_messages == [
        "This page contains chart or figure text. Please review the extracted "
        "text before generating audio."
    ]


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


def test_marks_interrupted_text_job_as_failed(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((20, 30)), "image/png"))],
        data={"rotations": "[0]"},
    ).json()
    document_id = LocalDocumentMetadataService().load(storage_path / upload["book_id"]).id
    service = DocumentTextProcessingService(
        storage_root=storage_path,
        ocr_provider=MockOcrProvider(),
    )
    service.prepare_document_job(document_id)

    service.mark_text_job_failed(document_id, "Library database timed out.")

    failed = service.load_document(document_id)
    assert failed.status == "failed"
    assert failed.error_message == "Library database timed out."
    assert failed.pages[0].processing_status == "failed"
    assert failed.pages[0].error_message == "Library database timed out."


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
