import os
import tempfile
from numbers import Real
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Protocol

from app.core.config import Settings
from app.core.errors import EchoError
from PIL import Image, ImageOps


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    y_min: float | None = None


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


class DisabledOcrProvider:
    """Clear runtime boundary for environments where real OCR is turned off."""

    def read_page(self, image_path: Path) -> OcrResult:
        raise EchoError(
            "ocr_disabled",
            "Page text reading is disabled in this development environment.",
            status_code=503,
        )


class PaddleOcrProvider:
    """PaddleOCR implementation, imported lazily so mock mode stays lightweight."""

    top_slice_height_ratio = 0.45
    top_slice_padding_ratio = 0.12
    top_slice_scale = 2

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
    def _line_y_min(box: Any) -> float | None:
        try:
            if len(box) == 4 and all(isinstance(value, Real) for value in box):
                return float(box[1])
            y_values = [float(point[1]) for point in box]
            return min(y_values) if y_values else None
        except (TypeError, ValueError, IndexError):
            return None

    @classmethod
    def _lines_from_prediction(cls, prediction: Any) -> list[OcrLine]:
        texts = prediction.get("rec_texts", [])
        scores = prediction.get("rec_scores", [])
        boxes = prediction.get("rec_boxes")
        if boxes is None:
            boxes = prediction.get("rec_polys")
        if boxes is None:
            boxes = []
        lines: list[OcrLine] = []
        for index, (text, score) in enumerate(zip(texts, scores, strict=False)):
            cleaned_text = str(text).strip()
            if cleaned_text:
                lines.append(
                    OcrLine(
                        text=cleaned_text,
                        confidence=max(0.0, min(1.0, float(score))),
                        y_min=(
                            cls._line_y_min(boxes[index])
                            if index < len(boxes)
                            else None
                        ),
                    )
                )
        return lines

    @staticmethod
    def _line_key(text: str) -> str:
        return "".join(character for character in text if not character.isspace())

    @classmethod
    def _first_body_line_y(cls, lines: list[OcrLine]) -> float | None:
        body_y_values: list[float] = []
        for line in lines:
            key = cls._line_key(line.text)
            if line.y_min is None:
                continue
            if len(key) <= 14 and not any(
                punctuation in line.text for punctuation in "，。！？；：「」『』"
            ):
                continue
            body_y_values.append(line.y_min)
        if body_y_values:
            return min(body_y_values)
        return lines[0].y_min if lines and lines[0].y_min is not None else None

    @classmethod
    def _merge_top_slice_lines(
        cls,
        top_lines: list[OcrLine],
        full_lines: list[OcrLine],
    ) -> list[OcrLine]:
        if not full_lines:
            return top_lines
        first_body_y = cls._first_body_line_y(full_lines)
        if first_body_y is None:
            return full_lines
        full_line_keys = {cls._line_key(line.text) for line in full_lines}
        prefix_lines = [
            line
            for line in top_lines
            if line.y_min is not None
            and line.y_min < first_body_y
            and cls._line_key(line.text) not in full_line_keys
        ]
        if not prefix_lines:
            return full_lines
        return prefix_lines + full_lines

    def _predict_lines(self, image_path: Path) -> list[OcrLine]:
        predictions = self._get_pipeline().predict(str(image_path))
        return [
            line
            for prediction in predictions
            for line in self._lines_from_prediction(prediction)
        ]

    def _read_top_slice_lines(self, image_path: Path) -> list[OcrLine]:
        try:
            with Image.open(image_path) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in {"RGB", "L"}:
                    normalized = normalized.convert("RGB")
                width, height = normalized.size
                if width < 100 or height < 100:
                    return []

                slice_bottom = max(1, round(height * self.top_slice_height_ratio))
                top_slice = normalized.crop((0, 0, width, slice_bottom))
                padding = max(8, round(slice_bottom * self.top_slice_padding_ratio))
                padded = ImageOps.expand(top_slice, border=padding, fill="white")
                enlarged = padded.resize(
                    (
                        padded.width * self.top_slice_scale,
                        padded.height * self.top_slice_scale,
                    ),
                    Image.Resampling.LANCZOS,
                )

                with tempfile.TemporaryDirectory() as temp_directory:
                    top_slice_path = Path(temp_directory) / "ocr-top-slice.png"
                    enlarged.save(top_slice_path, format="PNG")
                    return [
                        replace(
                            line,
                            y_min=(
                                max(
                                    0.0,
                                    (line.y_min / self.top_slice_scale) - padding,
                                )
                                if line.y_min is not None
                                else None
                            ),
                        )
                        for line in self._predict_lines(top_slice_path)
                    ]
        except OSError:
            return []

    def read_page(self, image_path: Path) -> OcrResult:
        if not image_path.is_file():
            raise EchoError(
                "page_image_missing",
                "Echo could not find the prepared page image.",
                status_code=404,
            )

        started_at = perf_counter()
        try:
            lines = self._predict_lines(image_path)
            top_lines = self._read_top_slice_lines(image_path)
            lines = self._merge_top_slice_lines(top_lines, lines)
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


def create_ocr_provider(settings: Settings) -> OcrProvider:
    """Choose the configured provider without leaking that choice into routes."""

    if settings.use_mock_ocr:
        return MockOcrProvider()
    if not settings.ocr_enabled:
        return DisabledOcrProvider()
    return PaddleOcrProvider(
        text_detection_model=settings.ocr_text_detection_model,
        text_recognition_model=settings.ocr_text_recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=settings.ocr_model_cache_path,
    )
