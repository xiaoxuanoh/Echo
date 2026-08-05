"""Evaluate cheap document-quality signals for missing OCR text risk.

Run from the repo root after approval with:
    ./backend/.venv/bin/python tmp/document_quality_signal/run_document_quality_signal.py

This is an isolated experiment. It does not modify Echo's production OCR
pipeline, PaddleOCR configuration, frontend, database, or documentation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from time import perf_counter

from PIL import Image, ImageFilter, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
OUTPUT_DIR = REPO_ROOT / "tmp" / "document_quality_signal" / "outputs"

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
UPPER_REGION_BOX = (50, 190, 960, 520)


@dataclass(frozen=True)
class QualityTarget:
    name: str
    path: Path
    purpose: str
    expected_suspicious: bool


@dataclass(frozen=True)
class QualitySignals:
    target_name: str
    processing_time_seconds: float
    width: int
    height: int
    dark_pixel_ratio: float
    text_region_coverage: float
    top_region_dark_ratio: float
    top_region_coverage: float
    body_region_coverage: float
    top_to_body_coverage_ratio: float
    empty_band_count: int
    max_empty_band_ratio: float
    blur_score: float
    shadow_score: float
    bleed_through_score: float
    skew_proxy_score: float


@dataclass(frozen=True)
class SignalRule:
    name: str
    description: str
    min_top_to_body_coverage_ratio: float | None = None
    min_top_region_coverage: float | None = None
    max_empty_band_ratio: float | None = None
    min_shadow_score: float | None = None
    min_bleed_through_score: float | None = None
    min_skew_proxy_score: float | None = None


@dataclass(frozen=True)
class RuleResult:
    rule_name: str
    target_name: str
    expected_suspicious: bool
    flagged_suspicious: bool
    correct: bool
    false_alarm: bool
    missed_suspicious: bool
    processing_time_seconds: float


def save_page_copy(source_path: Path, output_path: Path) -> None:
    with Image.open(source_path) as source:
        page = ImageOps.exif_transpose(source).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(output_path, format="PNG")


def prepare_targets() -> list[QualityTarget]:
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
        QualityTarget(
            name="difficult photographed page",
            path=difficult_page_path,
            purpose="known mobile OCR missed upper paragraph",
            expected_suspicious=True,
        ),
        QualityTarget(
            name="difficult upper paragraph region",
            path=difficult_region_path,
            purpose="known difficult crop, useful for signal stress testing",
            expected_suspicious=True,
        ),
        QualityTarget(
            name="normal scanned clean page",
            path=normal_page_path,
            purpose="normal page should avoid fallback signal",
            expected_suspicious=False,
        ),
        QualityTarget(
            name="mixed Chinese English finance page",
            path=mixed_page_path,
            purpose="mixed chart/text page should avoid language-specific assumptions",
            expected_suspicious=False,
        ),
    ]


def downsample_gray(image_path: Path, max_side: int = 900) -> Image.Image:
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


def row_dark_counts(image: Image.Image, threshold: int) -> list[int]:
    return [
        sum(1 for x in range(image.width) if image.getpixel((x, y)) < threshold)
        for y in range(image.height)
    ]


def column_dark_counts(image: Image.Image, threshold: int) -> list[int]:
    return [
        sum(1 for y in range(image.height) if image.getpixel((x, y)) < threshold)
        for x in range(image.width)
    ]


def robust_dark_threshold(image: Image.Image) -> int:
    histogram = image.histogram()
    darkest = next((index for index, count in enumerate(histogram) if count), 0)
    return min(210, max(120, darkest + 72))


def active_row_coverage(row_counts: list[int], width: int) -> float:
    if not row_counts:
        return 0.0
    min_dark_pixels = max(2, round(width * 0.012))
    active_rows = sum(1 for count in row_counts if count >= min_dark_pixels)
    return active_rows / len(row_counts)


def max_empty_band_ratio(row_counts: list[int], width: int) -> tuple[int, float]:
    min_dark_pixels = max(2, round(width * 0.010))
    max_run = 0
    current_run = 0
    band_count = 0
    in_band = False
    for count in row_counts:
        is_empty = count < min_dark_pixels
        if is_empty:
            current_run += 1
            if not in_band:
                band_count += 1
                in_band = True
        else:
            max_run = max(max_run, current_run)
            current_run = 0
            in_band = False
    max_run = max(max_run, current_run)
    return band_count, max_run / len(row_counts) if row_counts else 0.0


def blur_score(image: Image.Image) -> float:
    edges = image.filter(ImageFilter.FIND_EDGES)
    pixels = list(edges.getdata())
    return fmean(pixels) / 255 if pixels else 0.0


def shadow_score(image: Image.Image) -> float:
    small = image.resize((64, 64), Image.Resampling.BILINEAR)
    row_means = [
        fmean(small.getpixel((x, y)) for x in range(small.width))
        for y in range(small.height)
    ]
    column_means = [
        fmean(small.getpixel((x, y)) for y in range(small.height))
        for x in range(small.width)
    ]
    means = row_means + column_means
    return (max(means) - min(means)) / 255 if means else 0.0


def bleed_through_score(image: Image.Image) -> float:
    inverted = ImageOps.invert(image)
    blurred = inverted.filter(ImageFilter.GaussianBlur(radius=9))
    pixels = list(blurred.getdata())
    if not pixels:
        return 0.0
    midtone_pixels = [pixel for pixel in pixels if 18 <= pixel <= 90]
    return len(midtone_pixels) / len(pixels)


def skew_proxy_score(image: Image.Image, threshold: int) -> float:
    counts = column_dark_counts(image, threshold)
    if not counts:
        return 0.0
    left_half = counts[: len(counts) // 2]
    right_half = counts[len(counts) // 2 :]
    left_peak = max(left_half) if left_half else 0
    right_peak = max(right_half) if right_half else 0
    peak = max(left_peak, right_peak, 1)
    return abs(left_peak - right_peak) / peak


def measure_signals(target: QualityTarget) -> QualitySignals:
    started_at = perf_counter()
    gray = downsample_gray(target.path)
    threshold = robust_dark_threshold(gray)
    rows = row_dark_counts(gray, threshold)
    total_dark = sum(rows)
    dark_pixel_ratio = total_dark / (gray.width * gray.height)

    top = gray.crop((0, 0, gray.width, max(1, round(gray.height * 0.32))))
    body = gray.crop(
        (
            0,
            round(gray.height * 0.32),
            gray.width,
            max(round(gray.height * 0.32) + 1, round(gray.height * 0.78)),
        )
    )
    top_rows = row_dark_counts(top, threshold)
    body_rows = row_dark_counts(body, threshold)
    top_coverage = active_row_coverage(top_rows, gray.width)
    body_coverage = active_row_coverage(body_rows, gray.width)
    top_dark_ratio = sum(top_rows) / (top.width * top.height)
    empty_count, empty_ratio = max_empty_band_ratio(rows, gray.width)
    elapsed = perf_counter() - started_at

    return QualitySignals(
        target_name=target.name,
        processing_time_seconds=elapsed,
        width=gray.width,
        height=gray.height,
        dark_pixel_ratio=dark_pixel_ratio,
        text_region_coverage=active_row_coverage(rows, gray.width),
        top_region_dark_ratio=top_dark_ratio,
        top_region_coverage=top_coverage,
        body_region_coverage=body_coverage,
        top_to_body_coverage_ratio=top_coverage / body_coverage
        if body_coverage
        else math.inf,
        empty_band_count=empty_count,
        max_empty_band_ratio=empty_ratio,
        blur_score=blur_score(gray),
        shadow_score=shadow_score(gray),
        bleed_through_score=bleed_through_score(gray),
        skew_proxy_score=skew_proxy_score(gray, threshold),
    )


def signal_rules() -> list[SignalRule]:
    return [
        SignalRule(
            name="low top/body coverage",
            description="Flag pages where the top third has much less text-like coverage than the body.",
            min_top_to_body_coverage_ratio=0.65,
        ),
        SignalRule(
            name="sparse top region",
            description="Flag pages with very little text-like activity in the top region.",
            min_top_region_coverage=0.12,
        ),
        SignalRule(
            name="large empty band",
            description="Flag pages with a large internal empty band that may hide missed text.",
            max_empty_band_ratio=0.22,
        ),
        SignalRule(
            name="shadow or bleed-through",
            description="Flag pages with illumination or bleed-through risk.",
            min_shadow_score=0.34,
            min_bleed_through_score=0.20,
        ),
        SignalRule(
            name="skew proxy",
            description="Flag asymmetric dark-pixel distribution as a cheap skew/layout proxy.",
            min_skew_proxy_score=0.35,
        ),
    ]


def rule_flags(rule: SignalRule, signals: QualitySignals) -> bool:
    if (
        rule.min_top_to_body_coverage_ratio is not None
        and signals.top_to_body_coverage_ratio < rule.min_top_to_body_coverage_ratio
    ):
        return True
    if (
        rule.min_top_region_coverage is not None
        and signals.top_region_coverage < rule.min_top_region_coverage
    ):
        return True
    if (
        rule.max_empty_band_ratio is not None
        and signals.max_empty_band_ratio > rule.max_empty_band_ratio
    ):
        return True
    if (
        rule.min_shadow_score is not None
        and signals.shadow_score > rule.min_shadow_score
    ):
        return True
    if (
        rule.min_bleed_through_score is not None
        and signals.bleed_through_score > rule.min_bleed_through_score
    ):
        return True
    if (
        rule.min_skew_proxy_score is not None
        and signals.skew_proxy_score > rule.min_skew_proxy_score
    ):
        return True
    return False


def evaluate_rules(
    targets: list[QualityTarget],
    signals_by_target: dict[str, QualitySignals],
    rules: list[SignalRule],
) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in rules:
        for target in targets:
            signals = signals_by_target[target.name]
            flagged = rule_flags(rule, signals)
            results.append(
                RuleResult(
                    rule_name=rule.name,
                    target_name=target.name,
                    expected_suspicious=target.expected_suspicious,
                    flagged_suspicious=flagged,
                    correct=flagged == target.expected_suspicious,
                    false_alarm=flagged and not target.expected_suspicious,
                    missed_suspicious=(not flagged) and target.expected_suspicious,
                    processing_time_seconds=signals.processing_time_seconds,
                )
            )
    return results


def print_signal_table(signals: list[QualitySignals]) -> None:
    print("== Signal measurements ==")
    print(
        "target,time,width,height,dark_pixel_ratio,text_region_coverage,"
        "top_region_dark_ratio,top_region_coverage,body_region_coverage,"
        "top_to_body_coverage_ratio,empty_band_count,max_empty_band_ratio,"
        "blur_score,shadow_score,bleed_through_score,skew_proxy_score"
    )
    for signal in signals:
        print(
            f"{signal.target_name},{signal.processing_time_seconds:.4f},"
            f"{signal.width},{signal.height},{signal.dark_pixel_ratio:.4f},"
            f"{signal.text_region_coverage:.4f},{signal.top_region_dark_ratio:.4f},"
            f"{signal.top_region_coverage:.4f},{signal.body_region_coverage:.4f},"
            f"{signal.top_to_body_coverage_ratio:.4f},{signal.empty_band_count},"
            f"{signal.max_empty_band_ratio:.4f},{signal.blur_score:.4f},"
            f"{signal.shadow_score:.4f},{signal.bleed_through_score:.4f},"
            f"{signal.skew_proxy_score:.4f}"
        )


def print_rule_results(results: list[RuleResult], rules: list[SignalRule]) -> None:
    print("\n== Rule evaluation ==")
    print(
        "rule,target,expected_suspicious,flagged_suspicious,correct,"
        "false_alarm,missed_suspicious,processing_time_seconds"
    )
    for result in results:
        print(
            f"{result.rule_name},{result.target_name},{result.expected_suspicious},"
            f"{result.flagged_suspicious},{result.correct},{result.false_alarm},"
            f"{result.missed_suspicious},{result.processing_time_seconds:.4f}"
        )

    print("\n== Criteria tested ==")
    for rule in rules:
        print(f"- {rule.name}: {rule.description}")


def print_practicality_note(results: list[RuleResult]) -> None:
    average_cost = fmean(result.processing_time_seconds for result in results)
    print("\n== Practicality note ==")
    print(f"average_signal_processing_seconds={average_cost:.4f}")
    print(
        "language_independence=These signals use image structure, not recognized "
        "text, so they are candidates for multilingual pages. They still need "
        "validation on different layouts, scripts, charts, vertical text, and "
        "mixed-language books before they can control OCR fallback."
    )
    print(
        "architecture_prompt=If a signal reliably flags difficult pages with few "
        "false alarms, Echo can keep mobile OCR as default and route only flagged "
        "pages to slower fallback OCR in a background worker."
    )


def main() -> None:
    targets = prepare_targets()
    signals = [measure_signals(target) for target in targets]
    signals_by_target = {signal.target_name: signal for signal in signals}
    rules = signal_rules()
    results = evaluate_rules(targets, signals_by_target, rules)
    print_signal_table(signals)
    print_rule_results(results, rules)
    print_practicality_note(results)
    print(f"saved_target_images={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
