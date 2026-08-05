"""Detect possible missing OCR regions by comparing visual text bands to OCR lines.

Run from the repo root with:
    ./backend/.venv/bin/python tmp/ocr_gap_detection/run_ocr_gap_detection.py

This is an isolated experiment. It does not modify Echo's production OCR
pipeline or implement fallback logic.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median
from time import perf_counter

from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.ocr import OcrLine, PaddleOcrProvider  # noqa: E402


DIFFICULT_PAGE_IMAGE_PATH = (
    BACKEND_ROOT
    / "data"
    / "11ab953f-a194-42ed-b165-6349be45002c"
    / "pages"
    / "page-0001.png"
)
NORMAL_PAGE_IMAGE_PATH = (
    BACKEND_ROOT
    / "data"
    / "0f8631c5-cf41-4a65-8dea-14dff864c4b3"
    / "pages"
    / "page-0001.png"
)
MIXED_PAGE_IMAGE_PATH = (
    BACKEND_ROOT
    / "data"
    / "89523e10-28e7-4ddb-a97b-3d6a2f44e338"
    / "pages"
    / "page-0001.png"
)
OUTPUT_DIR = REPO_ROOT / "tmp" / "ocr_gap_detection" / "outputs"
MODEL_CACHE_DIR = BACKEND_ROOT / "data" / "models" / "paddlex"
UPPER_REGION_BOX = (50, 190, 960, 520)

KNOWN_UPPER_PARAGRAPH_LINES = [
    "業、醫療設備、金融業、核心科技或必需品消費股等。期",
    "權負責短期保障、鎖定收入和捕捉機會。即使面對戰爭陰",
    "霾或地緣衝突也不用恐慌賣出，而是從容調整。在動盪的",
    "2025年中，許多零售投資者正是因為這種組合，資產不跌",
    "反升，每月還有額外收入，真正實現財富自由。",
]


@dataclass(frozen=True)
class OcrGapTarget:
    name: str
    path: Path
    purpose: str
    expected_suspicious: bool
    expected_lines: list[str]


@dataclass(frozen=True)
class VisualBand:
    top: int
    bottom: int
    dark_pixel_ratio: float


@dataclass(frozen=True)
class GapResult:
    target_name: str
    expected_suspicious: bool
    flagged_suspicious: bool
    processing_time_seconds: float
    ocr_time_seconds: float
    visual_time_seconds: float
    ocr_line_count: int
    visual_band_count: int
    unmatched_band_count: int
    top_unmatched_band_count: int
    recovered_known_lines: int
    total_known_lines: int
    false_positive: bool
    missed_suspicious: bool


def compact(text: str) -> str:
    return "".join(text.split()).replace(",", "，").replace("·", "，")


def recovered_known_lines(lines: list[OcrLine], expected_lines: list[str]) -> list[str]:
    compact_text = compact("\n".join(line.text for line in lines))
    return [line for line in expected_lines if compact(line) in compact_text]


def save_page_copy(source_path: Path, output_path: Path) -> None:
    with Image.open(source_path) as source:
        page = ImageOps.exif_transpose(source).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(output_path, format="PNG")


def prepare_targets() -> list[OcrGapTarget]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(DIFFICULT_PAGE_IMAGE_PATH) as source:
        page = ImageOps.exif_transpose(source).convert("RGB")
        upper_region = page.crop(UPPER_REGION_BOX)

    difficult_page_path = OUTPUT_DIR / "01-difficult-original-page.png"
    difficult_region_path = OUTPUT_DIR / "02-difficult-upper-paragraph-region.png"
    normal_page_path = OUTPUT_DIR / "03-normal-clean-page.png"
    mixed_page_path = OUTPUT_DIR / "04-mixed-chinese-english-page.png"

    page.save(difficult_page_path, format="PNG")
    upper_region.save(difficult_region_path, format="PNG")
    save_page_copy(NORMAL_PAGE_IMAGE_PATH, normal_page_path)
    save_page_copy(MIXED_PAGE_IMAGE_PATH, mixed_page_path)

    return [
        OcrGapTarget(
            name="difficult photographed page",
            path=difficult_page_path,
            purpose="known mobile OCR missed upper paragraph on full page",
            expected_suspicious=True,
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
        ),
        OcrGapTarget(
            name="difficult upper paragraph region",
            path=difficult_region_path,
            purpose="known difficult crop where mobile OCR reads only lower lines",
            expected_suspicious=True,
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
        ),
        OcrGapTarget(
            name="normal scanned clean page",
            path=normal_page_path,
            purpose="normal text page should avoid suspicion",
            expected_suspicious=False,
            expected_lines=[],
        ),
        OcrGapTarget(
            name="mixed Chinese English finance page",
            path=mixed_page_path,
            purpose="mixed chart/text page should avoid broad false alarms",
            expected_suspicious=False,
            expected_lines=[],
        ),
    ]


def build_mobile_provider() -> PaddleOcrProvider:
    settings = Settings()
    return PaddleOcrProvider(
        text_detection_model=settings.ocr_text_detection_model,
        text_recognition_model=settings.ocr_text_recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=MODEL_CACHE_DIR,
    )


def robust_threshold(gray: Image.Image) -> int:
    histogram = gray.histogram()
    darkest = next((index for index, count in enumerate(histogram) if count), 0)
    return min(210, max(130, darkest + 74))


def text_bounds_from_dark_pixels(gray: Image.Image, threshold: int) -> tuple[int, int]:
    column_counts = [
        sum(1 for y in range(gray.height) if gray.getpixel((x, y)) < threshold)
        for x in range(gray.width)
    ]
    minimum = max(2, round(gray.height * 0.015))
    active_columns = [
        index for index, count in enumerate(column_counts) if count >= minimum
    ]
    if not active_columns:
        return round(gray.width * 0.08), round(gray.width * 0.92)
    padding = round(gray.width * 0.035)
    return (
        max(0, min(active_columns) - padding),
        min(gray.width, max(active_columns) + padding),
    )


def merge_segments(segments: list[tuple[int, int]], max_gap: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for top, bottom in segments:
        if not merged or top - merged[-1][1] > max_gap:
            merged.append((top, bottom))
        else:
            merged[-1] = (merged[-1][0], bottom)
    return merged


def detect_visual_bands(image_path: Path) -> list[VisualBand]:
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    gray = ImageOps.autocontrast(image)
    threshold = robust_threshold(gray)
    left, right = text_bounds_from_dark_pixels(gray, threshold)
    scan = gray.crop((left, 0, right, gray.height))
    row_counts = [
        sum(1 for x in range(scan.width) if scan.getpixel((x, y)) < threshold)
        for y in range(scan.height)
    ]
    if not row_counts:
        return []

    peak_count = max(row_counts)
    minimum_dark_pixels = max(3, round(scan.width * 0.012), round(peak_count * 0.09))
    smoothing_radius = max(1, round(scan.height * 0.0025))
    active_rows: list[bool] = []
    for index in range(len(row_counts)):
        start = max(0, index - smoothing_radius)
        stop = min(len(row_counts), index + smoothing_radius + 1)
        active_rows.append(fmean(row_counts[start:stop]) >= minimum_dark_pixels)

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

    minimum_height = max(4, round(scan.height * 0.004))
    merged = merge_segments(
        [
            segment
            for segment in raw_segments
            if segment[1] - segment[0] >= minimum_height
        ],
        max_gap=max(3, round(scan.height * 0.004)),
    )
    bands: list[VisualBand] = []
    for top, bottom in merged:
        band_counts = row_counts[top:bottom]
        if not band_counts:
            continue
        dark_ratio = sum(band_counts) / (scan.width * (bottom - top))
        if dark_ratio < 0.018:
            continue
        bands.append(VisualBand(top=top, bottom=bottom, dark_pixel_ratio=dark_ratio))
    return bands


def estimated_line_gap(lines: list[OcrLine], image_height: int) -> int:
    y_values = sorted(line.y_min for line in lines if line.y_min is not None)
    gaps = [
        later - earlier
        for earlier, later in zip(y_values, y_values[1:], strict=False)
        if 12 <= later - earlier <= image_height * 0.14
    ]
    if not gaps:
        return max(28, round(image_height * 0.035))
    return round(median(gaps))


def band_has_nearby_ocr_line(
    band: VisualBand,
    lines: list[OcrLine],
    *,
    line_gap: int,
) -> bool:
    slack = max(10, round(line_gap * 0.45))
    for line in lines:
        if line.y_min is None:
            continue
        if band.top - slack <= line.y_min <= band.bottom + slack:
            return True
    return False


def analyze_target(provider: PaddleOcrProvider, target: OcrGapTarget) -> GapResult:
    started_at = perf_counter()
    ocr_started_at = perf_counter()
    lines = provider._predict_lines(target.path)
    ocr_time = perf_counter() - ocr_started_at

    visual_started_at = perf_counter()
    visual_bands = detect_visual_bands(target.path)
    visual_time = perf_counter() - visual_started_at

    with Image.open(target.path) as source:
        height = ImageOps.exif_transpose(source).height
    line_gap = estimated_line_gap(lines, height)
    unmatched_bands = [
        band
        for band in visual_bands
        if not band_has_nearby_ocr_line(band, lines, line_gap=line_gap)
    ]
    top_cutoff = height * 0.36
    top_unmatched = [
        band
        for band in unmatched_bands
        if (band.top + band.bottom) / 2 <= top_cutoff
    ]
    recovered = recovered_known_lines(lines, target.expected_lines)
    flagged = len(top_unmatched) >= 2 or len(unmatched_bands) >= 3
    elapsed = perf_counter() - started_at
    return GapResult(
        target_name=target.name,
        expected_suspicious=target.expected_suspicious,
        flagged_suspicious=flagged,
        processing_time_seconds=elapsed,
        ocr_time_seconds=ocr_time,
        visual_time_seconds=visual_time,
        ocr_line_count=len(lines),
        visual_band_count=len(visual_bands),
        unmatched_band_count=len(unmatched_bands),
        top_unmatched_band_count=len(top_unmatched),
        recovered_known_lines=len(recovered),
        total_known_lines=len(target.expected_lines),
        false_positive=flagged and not target.expected_suspicious,
        missed_suspicious=(not flagged) and target.expected_suspicious,
    )


def print_result_table(results: list[GapResult]) -> None:
    print("== OCR gap detection summary ==")
    print(
        "target,expected_suspicious,flagged_suspicious,false_positive,"
        "missed_suspicious,recovered_known,total_known,ocr_lines,visual_bands,"
        "unmatched_bands,top_unmatched_bands,ocr_time,visual_time,total_time"
    )
    for result in results:
        print(
            f"{result.target_name},{result.expected_suspicious},"
            f"{result.flagged_suspicious},{result.false_positive},"
            f"{result.missed_suspicious},{result.recovered_known_lines},"
            f"{result.total_known_lines},{result.ocr_line_count},"
            f"{result.visual_band_count},{result.unmatched_band_count},"
            f"{result.top_unmatched_band_count},{result.ocr_time_seconds:.3f},"
            f"{result.visual_time_seconds:.3f},{result.processing_time_seconds:.3f}"
        )


def print_interpretation(results: list[GapResult]) -> None:
    correct = sum(
        1 for result in results if result.flagged_suspicious == result.expected_suspicious
    )
    false_positives = sum(1 for result in results if result.false_positive)
    missed = sum(1 for result in results if result.missed_suspicious)
    average_visual_cost = fmean(result.visual_time_seconds for result in results)
    print("\n== Interpretation prompts ==")
    print(f"detection_accuracy={correct}/{len(results)}")
    print(f"false_positives={false_positives}")
    print(f"missed_suspicious_pages={missed}")
    print(f"average_visual_gap_detection_seconds={average_visual_cost:.3f}")
    print(
        "fallback_trigger_question=If this signal flags the known difficult page "
        "without false positives on normal controls, it is a candidate trigger for "
        "selective server-detector fallback. If it misses the difficult page or "
        "flags normal pages, it needs a more precise visual-band/ocr-line matcher."
    )


def main() -> None:
    targets = prepare_targets()
    provider = build_mobile_provider()
    results = [analyze_target(provider, target) for target in targets]
    print_result_table(results)
    print_interpretation(results)
    print(f"saved_target_images={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
