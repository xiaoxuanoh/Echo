import os
import re
import tempfile
from difflib import SequenceMatcher
from numbers import Real
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Protocol

from app.core.config import Settings
from app.core.errors import EchoError
from PIL import Image, ImageEnhance, ImageOps


OCR_CJK_CHARACTER_PATTERN = re.compile(r"[\u3400-\u9fff]")
OCR_CJK_PROSE_PUNCTUATION_PATTERN = re.compile(r"[，。！？；：「」『』]")


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    y_min: float | None = None
    x_min: float | None = None
    x_max: float | None = None


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
    top_body_slice_top_ratio = 0.12
    top_body_slice_bottom_ratio = 0.58
    top_body_slice_scale = 3
    first_body_line_band_count = 5
    first_body_line_scale = 5
    recovery_first_body_y_ratio = 0.18

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
        bounds = PaddleOcrProvider._line_bounds(box)
        return bounds[1] if bounds is not None else None

    @staticmethod
    def _line_bounds(box: Any) -> tuple[float, float, float, float] | None:
        try:
            if len(box) == 4 and all(isinstance(value, Real) for value in box):
                left, top, right, bottom = [float(value) for value in box]
                return left, top, right, bottom
            x_values = [float(point[0]) for point in box]
            y_values = [float(point[1]) for point in box]
            if not x_values or not y_values:
                return None
            return min(x_values), min(y_values), max(x_values), max(y_values)
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
                bounds = cls._line_bounds(boxes[index]) if index < len(boxes) else None
                lines.append(
                    OcrLine(
                        text=cleaned_text,
                        confidence=max(0.0, min(1.0, float(score))),
                        y_min=bounds[1] if bounds is not None else None,
                        x_min=bounds[0] if bounds is not None else None,
                        x_max=bounds[2] if bounds is not None else None,
                    )
                )
        return lines

    @staticmethod
    def _line_key(text: str) -> str:
        return "".join(character for character in text if not character.isspace())

    @staticmethod
    def _is_auxiliary_noise_line(line: OcrLine) -> bool:
        text = line.text.strip()
        if len(text) <= 2 and not any(character.isalnum() for character in text):
            return True
        if line.confidence < 0.50 and len(text) <= 12:
            return True
        return False

    @classmethod
    def _is_similar_line(cls, first: str, second: str) -> bool:
        first_key = cls._line_key(first)
        second_key = cls._line_key(second)
        if first_key == second_key:
            return True
        if min(len(first_key), len(second_key)) < 10:
            return False
        return SequenceMatcher(None, first_key, second_key).ratio() >= 0.60

    @staticmethod
    def _better_recovered_line(first: OcrLine, second: OcrLine) -> OcrLine:
        if second.confidence > first.confidence:
            return second
        if second.confidence == first.confidence and len(second.text) > len(first.text):
            return second
        return first

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
    def _body_lines(cls, lines: list[OcrLine]) -> list[OcrLine]:
        return [
            line
            for line in lines
            if line.y_min is not None
            and len(cls._line_key(line.text)) > 14
            and (
                OCR_CJK_PROSE_PUNCTUATION_PATTERN.search(line.text)
                or len(OCR_CJK_CHARACTER_PATTERN.findall(line.text)) >= 8
            )
        ]

    @classmethod
    def _estimated_line_gap(cls, lines: list[OcrLine], image_height: int) -> int:
        body_y_values = sorted(
            line.y_min
            for line in cls._body_lines(lines)
            if line.y_min is not None and line.y_min < image_height * 0.60
        )
        gaps = [
            later - earlier
            for earlier, later in zip(body_y_values, body_y_values[1:], strict=False)
            if 15 <= later - earlier <= image_height * 0.12
        ]
        if not gaps:
            return max(32, round(image_height * 0.035))
        gaps.sort()
        return round(gaps[len(gaps) // 2])

    @classmethod
    def _text_block_bounds(
        cls,
        lines: list[OcrLine],
        *,
        image_width: int,
    ) -> tuple[int, int]:
        body_lines = [
            line
            for line in cls._body_lines(lines)
            if line.x_min is not None and line.x_max is not None
        ]
        if not body_lines:
            return round(image_width * 0.08), round(image_width * 0.96)
        left = min(line.x_min for line in body_lines if line.x_min is not None)
        right = max(line.x_max for line in body_lines if line.x_max is not None)
        padding = round(image_width * 0.04)
        return (
            max(0, round(left) - padding),
            min(image_width, round(right) + padding),
        )

    @classmethod
    def _has_short_header_above_first_body(
        cls,
        lines: list[OcrLine],
        *,
        first_body_y: float,
        image_height: int,
    ) -> bool:
        for line in lines:
            if line.y_min is None or line.y_min >= first_body_y:
                continue
            if line.y_min > image_height * 0.18:
                continue
            key = cls._line_key(line.text)
            if 4 <= len(key) <= 24:
                return True
        return False

    @classmethod
    def _should_run_top_recovery(
        cls,
        lines: list[OcrLine],
        *,
        image_height: int,
    ) -> bool:
        body_lines = cls._body_lines(lines)
        if not body_lines:
            return True
        first_body_y = min(
            line.y_min for line in body_lines if line.y_min is not None
        )
        if first_body_y > image_height * cls.recovery_first_body_y_ratio:
            return True
        if cls._has_short_header_above_first_body(
            lines,
            first_body_y=first_body_y,
            image_height=image_height,
        ):
            return True
        if len(body_lines) < 3 and first_body_y > image_height * 0.12:
            return True
        return False

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
        prefix_lines: list[OcrLine] = []
        for line in top_lines:
            key = cls._line_key(line.text)
            if (
                line.y_min is None
                or line.y_min >= first_body_y
                or cls._is_auxiliary_noise_line(line)
                or key in full_line_keys
                or any(cls._is_similar_line(line.text, full_line.text) for full_line in full_lines)
            ):
                continue
            similar_index = next(
                (
                    index
                    for index, prefix_line in enumerate(prefix_lines)
                    if cls._is_similar_line(line.text, prefix_line.text)
                ),
                None,
            )
            if similar_index is None:
                prefix_lines.append(line)
            else:
                prefix_lines[similar_index] = cls._better_recovered_line(
                    prefix_lines[similar_index],
                    line,
                )
        if not prefix_lines:
            return full_lines
        return sorted(
            prefix_lines + full_lines,
            key=lambda line: line.y_min if line.y_min is not None else float("inf"),
        )

    def _predict_lines(self, image_path: Path) -> list[OcrLine]:
        predictions = self._get_pipeline().predict(str(image_path))
        return [
            line
            for prediction in predictions
            for line in self._lines_from_prediction(prediction)
        ]

    @staticmethod
    def _enhance_top_region(image: Image.Image) -> Image.Image:
        enhanced = ImageOps.autocontrast(image)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.50)
        return ImageEnhance.Sharpness(enhanced).enhance(1.20)

    def _predict_cropped_lines(
        self,
        image: Image.Image,
        *,
        crop_left: int = 0,
        crop_right: int | None = None,
        crop_top: int,
        crop_bottom: int,
        padding: int,
        scale: int,
        filename: str,
        enhance: bool = False,
    ) -> list[OcrLine]:
        width, height = image.size
        bounded_left = max(0, min(width - 1, crop_left))
        bounded_right = max(bounded_left + 1, min(width, crop_right or width))
        bounded_top = max(0, min(height - 1, crop_top))
        bounded_bottom = max(bounded_top + 1, min(height, crop_bottom))
        cropped = image.crop(
            (bounded_left, bounded_top, bounded_right, bounded_bottom)
        )
        if enhance:
            cropped = self._enhance_top_region(cropped)
        padded = ImageOps.expand(cropped, border=padding, fill="white")
        enlarged = padded.resize(
            (
                padded.width * scale,
                padded.height * scale,
            ),
            Image.Resampling.LANCZOS,
        )

        with tempfile.TemporaryDirectory() as temp_directory:
            cropped_path = Path(temp_directory) / filename
            enlarged.save(cropped_path, format="PNG")
            return [
                replace(
                    line,
                    y_min=(
                        max(
                            0.0,
                            bounded_top + (line.y_min / scale) - padding,
                        )
                        if line.y_min is not None
                        else None
                    ),
                    x_min=(
                        max(
                            0.0,
                            bounded_left + (line.x_min / scale) - padding,
                        )
                        if line.x_min is not None
                        else None
                    ),
                    x_max=(
                        max(
                            0.0,
                            bounded_left + (line.x_max / scale) - padding,
                        )
                        if line.x_max is not None
                        else None
                    ),
                )
                for line in self._predict_lines(cropped_path)
            ]

    def _read_first_body_line_band_lines(
        self,
        image: Image.Image,
        full_lines: list[OcrLine],
    ) -> list[OcrLine]:
        width, height = image.size
        first_body_y = self._first_body_line_y(full_lines)
        if first_body_y is None:
            return []
        line_gap = self._estimated_line_gap(full_lines, height)
        band_height = max(48, round(line_gap * 1.7))
        scan_top = max(0, round(first_body_y - line_gap * 3.5))
        scan_bottom = min(height, round(first_body_y + line_gap * 0.35))
        if scan_bottom <= scan_top:
            return []

        left, right = self._text_block_bounds(full_lines, image_width=width)
        if self.first_body_line_band_count <= 1:
            band_tops = [scan_top]
        else:
            available = max(0, scan_bottom - scan_top - band_height)
            step = available / (self.first_body_line_band_count - 1)
            band_tops = [
                round(scan_top + step * index)
                for index in range(self.first_body_line_band_count)
            ]

        lines: list[OcrLine] = []
        for index, band_top in enumerate(band_tops, start=1):
            band_bottom = min(height, band_top + band_height)
            band_padding = max(80, round((band_bottom - band_top) * 0.40))
            lines.extend(
                self._predict_cropped_lines(
                    image,
                    crop_left=left,
                    crop_right=right,
                    crop_top=band_top,
                    crop_bottom=band_bottom,
                    padding=band_padding,
                    scale=self.first_body_line_scale,
                    filename=f"ocr-first-body-line-band-{index}.png",
                    enhance=True,
                )
            )
        return lines

    def _read_top_slice_lines(
        self,
        image_path: Path,
        full_lines: list[OcrLine],
    ) -> list[OcrLine]:
        try:
            with Image.open(image_path) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in {"RGB", "L"}:
                    normalized = normalized.convert("RGB")
                width, height = normalized.size
                if width < 100 or height < 100:
                    return []
                if not self._should_run_top_recovery(
                    full_lines,
                    image_height=height,
                ):
                    return []

                slice_bottom = max(1, round(height * self.top_slice_height_ratio))
                top_padding = max(8, round(slice_bottom * self.top_slice_padding_ratio))
                top_lines = self._predict_cropped_lines(
                    normalized,
                    crop_top=0,
                    crop_bottom=slice_bottom,
                    padding=top_padding,
                    scale=self.top_slice_scale,
                    filename="ocr-top-slice.png",
                )

                body_top = round(height * self.top_body_slice_top_ratio)
                body_bottom = round(height * self.top_body_slice_bottom_ratio)
                body_padding = max(8, round((body_bottom - body_top) * 0.08))
                body_lines = self._predict_cropped_lines(
                    normalized,
                    crop_top=body_top,
                    crop_bottom=body_bottom,
                    padding=body_padding,
                    scale=self.top_body_slice_scale,
                    filename="ocr-top-body-slice.png",
                    enhance=True,
                )

                first_line_lines = self._read_first_body_line_band_lines(
                    normalized,
                    full_lines,
                )

                return top_lines + body_lines + first_line_lines
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
            top_lines = self._read_top_slice_lines(image_path, lines)
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
