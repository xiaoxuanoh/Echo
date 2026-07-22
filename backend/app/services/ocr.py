import os
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Protocol

from app.core.errors import EchoError


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float


@dataclass(frozen=True)
class OcrResult:
    provider: str
    text: str
    lines: list[OcrLine]
    average_confidence: float | None
    processing_time_seconds: float


class OcrProvider(Protocol):
    """Replaceable boundary for reading text from one prepared page image."""

    def read_page(self, image_path: Path) -> OcrResult: ...


class MockOcrProvider:
    """Small local substitute that requires no model download or paid service."""

    def read_page(self, image_path: Path) -> OcrResult:
        if not image_path.is_file():
            raise EchoError(
                "page_image_missing",
                "Echo could not find the prepared page image.",
                status_code=404,
            )
        line = OcrLine(text="這是本地測試文字。", confidence=1.0)
        return OcrResult(
            provider="mock",
            text=line.text,
            lines=[line],
            average_confidence=1.0,
            processing_time_seconds=0.0,
        )


class PaddleOcrProvider:
    """PaddleOCR implementation, imported lazily so mock mode stays lightweight."""

    def __init__(
        self,
        *,
        text_detection_model: str,
        text_recognition_model: str,
        max_image_side: int,
        cache_path: Path,
    ) -> None:
        self.text_detection_model = text_detection_model
        self.text_recognition_model = text_recognition_model
        self.max_image_side = max_image_side
        self.cache_path = cache_path
        self._pipeline: Any | None = None

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        self.cache_path.mkdir(parents=True, exist_ok=True)
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(self.cache_path.resolve())
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise EchoError(
                "ocr_runtime_missing",
                "Real page text reading is not installed. Mock mode is still available.",
                status_code=503,
            ) from error

        try:
            self._pipeline = PaddleOCR(
                text_detection_model_name=self.text_detection_model,
                text_recognition_model_name=self.text_recognition_model,
                text_det_limit_side_len=self.max_image_side,
                text_det_limit_type="max",
                device="cpu",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as error:
            raise EchoError(
                "ocr_initialization_failed",
                "Echo could not start real page text reading.",
                status_code=503,
            ) from error
        return self._pipeline

    @staticmethod
    def _lines_from_prediction(prediction: Any) -> list[OcrLine]:
        texts = prediction.get("rec_texts", [])
        scores = prediction.get("rec_scores", [])
        lines: list[OcrLine] = []
        for text, score in zip(texts, scores, strict=False):
            cleaned_text = str(text).strip()
            if cleaned_text:
                lines.append(
                    OcrLine(
                        text=cleaned_text,
                        confidence=max(0.0, min(1.0, float(score))),
                    )
                )
        return lines

    def read_page(self, image_path: Path) -> OcrResult:
        if not image_path.is_file():
            raise EchoError(
                "page_image_missing",
                "Echo could not find the prepared page image.",
                status_code=404,
            )

        started_at = perf_counter()
        try:
            predictions = self._get_pipeline().predict(str(image_path))
            lines = [
                line
                for prediction in predictions
                for line in self._lines_from_prediction(prediction)
            ]
        except EchoError:
            raise
        except Exception as error:
            raise EchoError(
                "ocr_failed",
                "Echo could not read the text on this page.",
                status_code=500,
            ) from error

        return OcrResult(
            provider="paddleocr",
            text="\n".join(line.text for line in lines),
            lines=lines,
            average_confidence=(
                fmean(line.confidence for line in lines) if lines else None
            ),
            processing_time_seconds=perf_counter() - started_at,
        )
