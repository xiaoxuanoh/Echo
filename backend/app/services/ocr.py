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
    warnings: list[str] | None = None


@dataclass(frozen=True)
class OcrCropBand:
    top: int
    bottom: int


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
    first_body_line_max_crop_count = 10
    top_paragraph_scale = 4
    visual_slot_min_confidence = 0.86
    visual_band_scan_gap_count = 4.0
    visual_band_min_dark_pixel_ratio = 0.012
    visual_band_peak_ratio = 0.08
    recovery_first_body_y_ratio = 0.18
    auxiliary_min_confidence = 0.90
    auxiliary_left_alignment_ratio = 0.06
    uncertain_text_warning = (
        "Echo found possible text near the top of this page, but it may contain "
        "OCR mistakes. Please review this page before listening."
    )

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
    def _is_trustworthy_auxiliary_line(
        cls,
        line: OcrLine,
        *,
        text_block_left: int,
        image_width: int,
    ) -> bool:
        if line.confidence < cls.auxiliary_min_confidence:
            return False
        if line.x_min is None:
            return False
        left_slack = max(20, image_width * cls.auxiliary_left_alignment_ratio)
        if line.x_min > text_block_left + left_slack:
            return False
        return True

    @classmethod
    def _is_plausible_recovered_body_line(cls, line: OcrLine) -> bool:
        key = cls._line_key(line.text)
        if len(key) < 12:
            return False
        if len(OCR_CJK_CHARACTER_PATTERN.findall(line.text)) < 8:
            return False
        return True

    @staticmethod
    def _line_matches_visual_band(
        line: OcrLine,
        band: OcrCropBand,
        *,
        line_gap: int,
    ) -> bool:
        if line.y_min is None:
            return False
        slack = max(10, round(line_gap * 0.45))
        return band.top - slack <= line.y_min <= band.bottom + slack

    @classmethod
    def _line_slots_from_visual_bands(
        cls,
        bands: list[OcrCropBand],
        *,
        line_gap: int,
    ) -> list[OcrCropBand]:
        slots: list[OcrCropBand] = []
        for band in bands:
            band_height = band.bottom - band.top
            if band_height <= line_gap * 1.35:
                slots.append(band)
                continue
            slot_count = max(1, round(band_height / line_gap))
            slot_height = band_height / slot_count
            for index in range(slot_count):
                slots.append(
                    OcrCropBand(
                        top=round(band.top + slot_height * index),
                        bottom=round(band.top + slot_height * (index + 1)),
                    )
                )
        return slots

    @staticmethod
    def _unique_crop_bands(bands: list[OcrCropBand]) -> list[OcrCropBand]:
        unique_bands: list[OcrCropBand] = []
        seen: set[tuple[int, int]] = set()
        for band in bands:
            key = (band.top, band.bottom)
            if key in seen:
                continue
            seen.add(key)
            unique_bands.append(band)
        return unique_bands

    @classmethod
    def _is_slot_fill_candidate(
        cls,
        line: OcrLine,
        *,
        text_block_left: int,
        image_width: int,
    ) -> bool:
        if line.confidence < cls.visual_slot_min_confidence:
            return False
        if not cls._is_plausible_recovered_body_line(line):
            return False
        if line.x_min is None:
            return False
        left_slack = max(48, image_width * cls.auxiliary_left_alignment_ratio * 1.8)
        if line.x_min > text_block_left + left_slack:
            return False
        return True

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
    def _merge_close_row_segments(
        cls,
        segments: list[tuple[int, int]],
        *,
        max_gap: int,
    ) -> list[tuple[int, int]]:
        merged: list[tuple[int, int]] = []
        for top, bottom in segments:
            if not merged or top - merged[-1][1] > max_gap:
                merged.append((top, bottom))
                continue
            merged[-1] = (merged[-1][0], bottom)
        return merged

    @classmethod
    def _detect_visual_text_bands(
        cls,
        image: Image.Image,
        full_lines: list[OcrLine],
    ) -> list[OcrCropBand]:
        width, height = image.size
        first_body_y = cls._first_body_line_y(full_lines)
        if first_body_y is None:
            return []
        line_gap = cls._estimated_line_gap(full_lines, height)
        left, right = cls._text_block_bounds(full_lines, image_width=width)
        if right - left < width * 0.20:
            return []

        scan_top = max(
            0,
            round(first_body_y - line_gap * cls.visual_band_scan_gap_count),
        )
        scan_bottom = min(height, round(first_body_y + line_gap * 0.45))
        if scan_bottom - scan_top < max(24, line_gap):
            return []

        scan = image.crop((left, scan_top, right, scan_bottom)).convert("L")
        scan = ImageOps.autocontrast(scan)
        histogram = scan.histogram()
        if not histogram:
            return []
        darkest = next(
            (index for index, count in enumerate(histogram) if count),
            255,
        )
        if darkest > 230:
            return []
        threshold = min(235, max(160, darkest + 80))
        row_counts = [
            sum(1 for x in range(scan.width) if scan.getpixel((x, y)) < threshold)
            for y in range(scan.height)
        ]
        if not row_counts:
            return []
        peak_count = max(row_counts)
        min_dark_pixels = max(
            2,
            round(scan.width * cls.visual_band_min_dark_pixel_ratio),
            round(peak_count * cls.visual_band_peak_ratio),
        )

        smoothing_radius = max(1, round(line_gap * 0.05))
        active_rows: list[bool] = []
        for index in range(len(row_counts)):
            start = max(0, index - smoothing_radius)
            stop = min(len(row_counts), index + smoothing_radius + 1)
            smoothed = sum(row_counts[start:stop]) / (stop - start)
            active_rows.append(smoothed >= min_dark_pixels)

        raw_segments: list[tuple[int, int]] = []
        segment_start: int | None = None
        for index, is_active in enumerate(active_rows):
            if is_active and segment_start is None:
                segment_start = index
            elif not is_active and segment_start is not None:
                raw_segments.append((segment_start, index))
                segment_start = None
        if segment_start is not None:
            raw_segments.append((segment_start, len(active_rows)))

        minimum_segment_height = max(4, round(line_gap * 0.16))
        segments = [
            segment
            for segment in raw_segments
            if segment[1] - segment[0] >= minimum_segment_height
        ]
        segments = cls._merge_close_row_segments(
            segments,
            max_gap=max(3, round(line_gap * 0.18)),
        )

        padding = max(8, round(line_gap * 0.45))
        bands: list[OcrCropBand] = []
        for top, bottom in segments:
            absolute_top = max(0, scan_top + top - padding)
            absolute_bottom = min(height, scan_top + bottom + padding)
            if absolute_bottom - absolute_top < max(24, round(line_gap * 0.60)):
                continue
            center_y = (absolute_top + absolute_bottom) / 2
            if center_y > first_body_y + line_gap * 0.30:
                continue
            bands.append(OcrCropBand(top=absolute_top, bottom=absolute_bottom))
        return bands[: cls.first_body_line_band_count]

    @classmethod
    def _estimated_first_body_crop_bands(
        cls,
        *,
        first_body_y: float,
        line_gap: int,
        image_height: int,
    ) -> list[OcrCropBand]:
        scan_top = max(0, round(first_body_y - line_gap * 3.5))
        scan_bottom = min(image_height, round(first_body_y + line_gap * 0.35))
        if scan_bottom <= scan_top:
            return []

        band_height = max(48, round(line_gap * 1.7))
        if cls.first_body_line_band_count <= 1:
            band_tops = [scan_top]
        else:
            available = max(0, scan_bottom - scan_top - band_height)
            step = available / (cls.first_body_line_band_count - 1)
            band_tops = [
                round(scan_top + step * index)
                for index in range(cls.first_body_line_band_count)
            ]
        return [
            OcrCropBand(
                top=band_top,
                bottom=min(image_height, band_top + band_height),
            )
            for band_top in band_tops
        ]

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
    def _has_visual_text_above_first_body(
        cls,
        image: Image.Image,
        lines: list[OcrLine],
    ) -> bool:
        first_body_y = cls._first_body_line_y(lines)
        if first_body_y is None:
            return False
        line_gap = cls._estimated_line_gap(lines, image.size[1])
        cutoff_y = first_body_y - max(8, line_gap * 0.20)
        for band in cls._detect_visual_text_bands(image, lines):
            center_y = (band.top + band.bottom) / 2
            if center_y < cutoff_y:
                return True
        return False

    @classmethod
    def _should_run_top_recovery(
        cls,
        lines: list[OcrLine],
        *,
        image_height: int,
        has_visual_text_above_first_body: bool = False,
    ) -> bool:
        if has_visual_text_above_first_body:
            return True
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
        *,
        image_width: int | None = None,
        image_height: int | None = None,
        visual_bands: list[OcrCropBand] | None = None,
    ) -> tuple[list[OcrLine], list[str]]:
        if not full_lines:
            return top_lines, []
        first_body_y = cls._first_body_line_y(full_lines)
        if first_body_y is None:
            return full_lines, []
        line_gap = cls._estimated_line_gap(full_lines, image_height or 1000)
        text_block_left, _ = cls._text_block_bounds(
            full_lines,
            image_width=image_width or 1000,
        )
        full_line_keys = {cls._line_key(line.text) for line in full_lines}
        prefix_lines: list[OcrLine] = []
        rejected_lines: list[OcrLine] = []
        for line in top_lines:
            key = cls._line_key(line.text)
            if (
                line.y_min is None
                or line.y_min >= first_body_y
                or cls._is_auxiliary_noise_line(line)
                or key in full_line_keys
                or any(
                    cls._is_similar_line(line.text, full_line.text)
                    for full_line in full_lines
                )
            ):
                continue
            if not cls._is_trustworthy_auxiliary_line(
                line,
                text_block_left=text_block_left,
                image_width=image_width or 1000,
            ):
                rejected_lines.append(line)
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
                better_line = cls._better_recovered_line(
                    prefix_lines[similar_index],
                    line,
                )
                if not cls._is_trustworthy_auxiliary_line(
                    better_line,
                    text_block_left=text_block_left,
                    image_width=image_width or 1000,
                ):
                    rejected_lines.append(better_line)
                    continue
                prefix_lines[similar_index] = better_line
        visual_slots = cls._line_slots_from_visual_bands(
            visual_bands or [],
            line_gap=line_gap,
        )
        expected_bands = [
            band
            for band in visual_slots
            if (band.top + band.bottom) / 2 < first_body_y - max(8, line_gap * 0.20)
        ]
        for band in expected_bands:
            if any(
                cls._line_matches_visual_band(
                    prefix_line,
                    band,
                    line_gap=line_gap,
                )
                for prefix_line in prefix_lines
            ):
                continue
            slot_candidates = [
                line
                for line in rejected_lines + top_lines
                if line.y_min is not None
                and line.y_min < first_body_y
                and cls._line_matches_visual_band(line, band, line_gap=line_gap)
                and cls._is_slot_fill_candidate(
                    line,
                    text_block_left=text_block_left,
                    image_width=image_width or 1000,
                )
                and cls._line_key(line.text) not in full_line_keys
                and not any(
                    cls._is_similar_line(line.text, existing_line.text)
                    for existing_line in full_lines + prefix_lines
                )
            ]
            if not slot_candidates:
                continue
            prefix_lines.append(
                max(
                    slot_candidates,
                    key=lambda line: (
                        line.confidence,
                        len(cls._line_key(line.text)),
                    ),
                )
            )
        warnings = (
            [cls.uncertain_text_warning]
            if any(
                not any(
                    cls._is_similar_line(rejected_line.text, prefix_line.text)
                    for prefix_line in prefix_lines
                )
                for rejected_line in rejected_lines
            )
            else []
        )
        if not prefix_lines:
            return full_lines, warnings
        return (
            sorted(
                prefix_lines + full_lines,
                key=lambda line: line.y_min if line.y_min is not None else float("inf"),
            ),
            warnings,
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
        estimated_bands = self._estimated_first_body_crop_bands(
            first_body_y=first_body_y,
            line_gap=line_gap,
            image_height=height,
        )
        if not estimated_bands:
            return []

        left, right = self._text_block_bounds(full_lines, image_width=width)
        visual_bands = self._detect_visual_text_bands(image, full_lines)
        visual_slots = self._line_slots_from_visual_bands(
            visual_bands,
            line_gap=line_gap,
        )
        crop_bands = self._unique_crop_bands(
            visual_slots + visual_bands + estimated_bands
        )[
            : self.first_body_line_max_crop_count
        ]

        lines: list[OcrLine] = []
        for index, band in enumerate(crop_bands, start=1):
            band_padding = max(80, round((band.bottom - band.top) * 0.40))
            lines.extend(
                self._predict_cropped_lines(
                    image,
                    crop_left=left,
                    crop_right=right,
                    crop_top=band.top,
                    crop_bottom=band.bottom,
                    padding=band_padding,
                    scale=self.first_body_line_scale,
                    filename=f"ocr-first-body-line-band-{index}.png",
                    enhance=True,
                )
            )
        return lines

    def _read_top_paragraph_lines(
        self,
        image: Image.Image,
        full_lines: list[OcrLine],
        visual_bands: list[OcrCropBand],
    ) -> list[OcrLine]:
        width, height = image.size
        first_body_y = self._first_body_line_y(full_lines)
        if first_body_y is None:
            return []
        line_gap = self._estimated_line_gap(full_lines, height)
        prefix_bands = [
            band
            for band in visual_bands
            if (band.top + band.bottom) / 2 < first_body_y - max(8, line_gap * 0.20)
        ]
        if not prefix_bands:
            return []

        left, right = self._text_block_bounds(full_lines, image_width=width)
        crop_top = max(
            0,
            min(band.top for band in prefix_bands) - round(line_gap * 0.80),
        )
        crop_bottom = min(
            height,
            max(band.bottom for band in prefix_bands) + round(line_gap * 0.80),
        )
        if crop_bottom - crop_top < max(36, round(line_gap * 1.2)):
            return []

        padding = max(80, round((crop_bottom - crop_top) * 0.30))
        return self._predict_cropped_lines(
            image,
            crop_left=left,
            crop_right=right,
            crop_top=crop_top,
            crop_bottom=crop_bottom,
            padding=padding,
            scale=self.top_paragraph_scale,
            filename="ocr-top-paragraph.png",
            enhance=True,
        )

    def _read_top_slice_lines(
        self,
        image_path: Path,
        full_lines: list[OcrLine],
    ) -> tuple[list[OcrLine], list[OcrCropBand]]:
        try:
            with Image.open(image_path) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in {"RGB", "L"}:
                    normalized = normalized.convert("RGB")
                width, height = normalized.size
                if width < 100 or height < 100:
                    return [], []
                visual_bands = self._detect_visual_text_bands(
                    normalized,
                    full_lines,
                )
                if not self._should_run_top_recovery(
                    full_lines,
                    image_height=height,
                    has_visual_text_above_first_body=(
                        self._has_visual_text_above_first_body(normalized, full_lines)
                    ),
                ):
                    return [], visual_bands

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
                paragraph_lines = self._read_top_paragraph_lines(
                    normalized,
                    full_lines,
                    visual_bands,
                )

                return (
                    top_lines + body_lines + first_line_lines + paragraph_lines,
                    visual_bands,
                )
        except OSError:
            return [], []

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
            image_width: int | None = None
            image_height: int | None = None
            try:
                with Image.open(image_path) as image:
                    image_width, image_height = image.size
            except OSError:
                image_width = None
                image_height = None
            top_lines, visual_bands = self._read_top_slice_lines(image_path, lines)
            lines, warnings = self._merge_top_slice_lines(
                top_lines,
                lines,
                image_width=image_width,
                image_height=image_height,
                visual_bands=visual_bands,
            )
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
            warnings=warnings,
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
