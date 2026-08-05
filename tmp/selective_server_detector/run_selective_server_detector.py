"""Evaluate selective PaddleOCR server-detector fallback.

Run from the repo root after approval with:
    ./backend/.venv/bin/python tmp/selective_server_detector/run_selective_server_detector.py

This is an isolated experiment. It does not modify Echo's production OCR
pipeline or settings.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from time import perf_counter

from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.ocr import PaddleOcrProvider  # noqa: E402


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
OUTPUT_DIR = REPO_ROOT / "tmp" / "selective_server_detector" / "outputs"
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
class OcrTarget:
    name: str
    path: Path
    purpose: str
    expected_lines: list[str]
    should_need_fallback: bool


@dataclass(frozen=True)
class OcrRun:
    engine: str
    target_name: str
    processing_time_seconds: float
    lines: list[str]
    confidences: list[float]


@dataclass(frozen=True)
class FallbackRule:
    name: str
    description: str
    min_recovered_known_lines: int | None = None
    min_line_count: int | None = None
    min_average_confidence: float | None = None
    trigger_if_top_expected_missing: bool = False


@dataclass(frozen=True)
class DecisionResult:
    rule_name: str
    target_name: str
    escalated: bool
    unnecessary_fallback: bool
    missed_needed_fallback: bool
    recovered_known_mobile: int
    recovered_known_final: int
    final_line_count: int
    final_average_confidence: float | None
    total_processing_time_seconds: float
    selected_engine: str


def compact(text: str) -> str:
    return "".join(text.split()).replace(",", "，").replace("·", "，")


def recovered_known_lines(text: str, expected_lines: list[str]) -> list[str]:
    compact_text = compact(text)
    return [line for line in expected_lines if compact(line) in compact_text]


def average_confidence(confidences: list[float]) -> float | None:
    return fmean(confidences) if confidences else None


def likely_noise(lines: list[str], confidences: list[float]) -> list[str]:
    noisy: list[str] = []
    for line, confidence in zip(lines, confidences, strict=False):
        if confidence < 0.75:
            noisy.append(line)
            continue
        ascii_letters = sum(
            character.isascii() and character.isalpha()
            for character in line
        )
        if ascii_letters >= 2:
            noisy.append(line)
    return noisy


def save_page_copy(source_path: Path, output_path: Path) -> None:
    with Image.open(source_path) as source:
        page = ImageOps.exif_transpose(source).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(output_path, format="PNG")


def prepare_targets() -> list[OcrTarget]:
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
        OcrTarget(
            name="difficult photographed page",
            path=difficult_page_path,
            purpose="known missed upper paragraph on full page",
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
            should_need_fallback=True,
        ),
        OcrTarget(
            name="difficult upper paragraph region",
            path=difficult_region_path,
            purpose="isolated known difficult region",
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
            should_need_fallback=True,
        ),
        OcrTarget(
            name="normal scanned clean page",
            path=normal_page_path,
            purpose="normal text page should avoid fallback",
            expected_lines=[],
            should_need_fallback=False,
        ),
        OcrTarget(
            name="mixed Chinese English finance page",
            path=mixed_page_path,
            purpose="mixed-language/chart page should avoid fallback unless mobile is weak",
            expected_lines=[],
            should_need_fallback=False,
        ),
    ]


def fallback_rules() -> list[FallbackRule]:
    return [
        FallbackRule(
            name="known-line recall gate",
            description=(
                "Experiment-only oracle rule: escalate if known difficult text "
                "recovery is below expected. This estimates the upper bound of a "
                "good production detector."
            ),
            min_recovered_known_lines=4,
        ),
        FallbackRule(
            name="low line count gate",
            description="Escalate when OCR returns too few lines for the target image.",
            min_line_count=4,
        ),
        FallbackRule(
            name="confidence gate",
            description="Escalate when average OCR confidence is suspiciously low.",
            min_average_confidence=0.94,
        ),
        FallbackRule(
            name="top-region missing gate",
            description=(
                "Escalate if expected top-region text is missing. This simulates a "
                "future visual/text-layout suspicion heuristic."
            ),
            trigger_if_top_expected_missing=True,
        ),
    ]


def build_provider(*, detection_model: str, recognition_model: str) -> PaddleOcrProvider:
    settings = Settings()
    return PaddleOcrProvider(
        text_detection_model=detection_model,
        text_recognition_model=recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=MODEL_CACHE_DIR,
    )


def run_ocr(provider: PaddleOcrProvider, engine: str, target: OcrTarget) -> OcrRun:
    started_at = perf_counter()
    lines = provider._predict_lines(target.path)
    elapsed = perf_counter() - started_at
    return OcrRun(
        engine=engine,
        target_name=target.name,
        processing_time_seconds=elapsed,
        lines=[line.text for line in lines],
        confidences=[line.confidence for line in lines],
    )


def should_escalate(rule: FallbackRule, mobile_run: OcrRun, target: OcrTarget) -> bool:
    text = "\n".join(mobile_run.lines)
    recovered_count = len(recovered_known_lines(text, target.expected_lines))
    average = average_confidence(mobile_run.confidences)
    if (
        rule.min_recovered_known_lines is not None
        and target.expected_lines
        and recovered_count < rule.min_recovered_known_lines
    ):
        return True
    if rule.min_line_count is not None and len(mobile_run.lines) < rule.min_line_count:
        return True
    if (
        rule.min_average_confidence is not None
        and average is not None
        and average < rule.min_average_confidence
    ):
        return True
    if (
        rule.trigger_if_top_expected_missing
        and target.expected_lines
        and recovered_count < len(target.expected_lines)
    ):
        return True
    return False


def evaluate_rule(
    rule: FallbackRule,
    target: OcrTarget,
    mobile_run: OcrRun,
    server_run: OcrRun,
) -> DecisionResult:
    escalated = should_escalate(rule, mobile_run, target)
    final_run = server_run if escalated else mobile_run
    mobile_text = "\n".join(mobile_run.lines)
    final_text = "\n".join(final_run.lines)
    recovered_mobile = len(
        recovered_known_lines(mobile_text, target.expected_lines)
    )
    recovered_final = len(recovered_known_lines(final_text, target.expected_lines))
    average = average_confidence(final_run.confidences)
    return DecisionResult(
        rule_name=rule.name,
        target_name=target.name,
        escalated=escalated,
        unnecessary_fallback=escalated and not target.should_need_fallback,
        missed_needed_fallback=(not escalated) and target.should_need_fallback,
        recovered_known_mobile=recovered_mobile,
        recovered_known_final=recovered_final,
        final_line_count=len(final_run.lines),
        final_average_confidence=average,
        total_processing_time_seconds=(
            mobile_run.processing_time_seconds
            + (server_run.processing_time_seconds if escalated else 0.0)
        ),
        selected_engine=final_run.engine,
    )


def print_run_result(run: OcrRun, target: OcrTarget) -> None:
    text = "\n".join(run.lines)
    recovered = recovered_known_lines(text, target.expected_lines)
    noise = likely_noise(run.lines, run.confidences)
    average = average_confidence(run.confidences)
    print(f"\n== {run.engine}: {target.name} ==")
    print(f"target_purpose={target.purpose}")
    print(f"processing_time_seconds={run.processing_time_seconds:.3f}")
    print(f"line_count={len(run.lines)}")
    print(f"average_confidence={average:.3f}" if average is not None else "average_confidence=n/a")
    if target.expected_lines:
        print(f"recovered_known_lines={len(recovered)}/{len(target.expected_lines)}")
    else:
        print("recovered_known_lines=not measured for this sample")
    print(f"likely_noise_count={len(noise)}")


def print_decision_summary(results: list[DecisionResult], rules: list[FallbackRule]) -> None:
    print("\n== Selective fallback summary ==")
    print(
        "rule,target,escalated,unnecessary_fallback,missed_needed_fallback,"
        "recovered_known_mobile,recovered_known_final,final_line_count,"
        "final_average_confidence,total_processing_time_seconds,selected_engine"
    )
    for result in results:
        confidence = (
            f"{result.final_average_confidence:.3f}"
            if result.final_average_confidence is not None
            else "n/a"
        )
        print(
            f"{result.rule_name},{result.target_name},{result.escalated},"
            f"{result.unnecessary_fallback},{result.missed_needed_fallback},"
            f"{result.recovered_known_mobile},{result.recovered_known_final},"
            f"{result.final_line_count},{confidence},"
            f"{result.total_processing_time_seconds:.3f},{result.selected_engine}"
        )

    print("\n== Escalation criteria tested ==")
    for rule in rules:
        print(f"- {rule.name}: {rule.description}")


def print_speed_baselines(mobile_runs: list[OcrRun], server_runs: list[OcrRun]) -> None:
    always_mobile = sum(run.processing_time_seconds for run in mobile_runs)
    always_server = sum(run.processing_time_seconds for run in server_runs)
    page_count = len(mobile_runs)
    print("\n== Speed baselines ==")
    print(f"always_mobile_total_seconds={always_mobile:.3f}")
    print(f"always_mobile_average_seconds={always_mobile / page_count:.3f}")
    print(f"always_server_total_seconds={always_server:.3f}")
    print(f"always_server_average_seconds={always_server / page_count:.3f}")
    print(
        "cpu_practicality_note=selective fallback should be judged against these "
        "baselines; server detector fallback may require background jobs and worker "
        "limits if several users upload page batches concurrently."
    )


def main() -> None:
    settings = Settings()
    targets = prepare_targets()
    rules = fallback_rules()
    mobile_provider = build_provider(
        detection_model=settings.ocr_text_detection_model,
        recognition_model=settings.ocr_text_recognition_model,
    )
    server_provider = build_provider(
        detection_model="PP-OCRv5_server_det",
        recognition_model=settings.ocr_text_recognition_model,
    )

    mobile_runs = [
        run_ocr(mobile_provider, "mobile det + mobile rec", target)
        for target in targets
    ]
    server_runs = [
        run_ocr(server_provider, "server det + mobile rec", target)
        for target in targets
    ]

    for target, mobile_run, server_run in zip(
        targets,
        mobile_runs,
        server_runs,
        strict=True,
    ):
        print_run_result(mobile_run, target)
        print_run_result(server_run, target)

    decisions: list[DecisionResult] = []
    for rule in rules:
        for target, mobile_run, server_run in zip(
            targets,
            mobile_runs,
            server_runs,
            strict=True,
        ):
            decisions.append(evaluate_rule(rule, target, mobile_run, server_run))

    print_speed_baselines(mobile_runs, server_runs)
    print_decision_summary(decisions, rules)
    print(
        "\nrecommendation_prompt=Prefer criteria that recover known missed text while "
        "avoiding fallback on normal and mixed-language samples. If useful criteria "
        "depend on oracle known text, translate them into production-observable "
        "signals before considering Echo architecture changes."
    )
    print(f"saved_target_images={OUTPUT_DIR}")


if __name__ == "__main__":
    main()
