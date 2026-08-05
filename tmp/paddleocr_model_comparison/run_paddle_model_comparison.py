"""Compare PaddleOCR model configurations on representative Echo pages.

Run from the repo root after approval with:
    ./backend/.venv/bin/python tmp/paddleocr_model_comparison/run_paddle_model_comparison.py

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
OUTPUT_DIR = REPO_ROOT / "tmp" / "paddleocr_model_comparison" / "outputs"
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
class PaddleModelConfig:
    name: str
    detection_model: str
    recognition_model: str
    max_image_side: int
    purpose: str
    expected_implication: str
    deployment_note: str


@dataclass(frozen=True)
class OcrTarget:
    name: str
    path: Path
    purpose: str
    expected_lines: list[str]


@dataclass(frozen=True)
class PaddleRunResult:
    config_name: str
    target_name: str
    detection_model: str
    recognition_model: str
    max_image_side: int
    purpose: str
    expected_implication: str
    deployment_note: str
    processing_time_seconds: float | None
    lines: list[str]
    confidences: list[float | None]
    unavailable_reason: str | None = None


def compact(text: str) -> str:
    return "".join(text.split()).replace(",", "，").replace("·", "，")


def recovered_known_lines(text: str, expected_lines: list[str]) -> list[str]:
    compact_text = compact(text)
    return [line for line in expected_lines if compact(line) in compact_text]


def missing_known_lines(text: str, expected_lines: list[str]) -> list[str]:
    recovered = set(recovered_known_lines(text, expected_lines))
    return [line for line in expected_lines if line not in recovered]


def likely_noise(lines: list[str], confidences: list[float | None]) -> list[str]:
    noisy: list[str] = []
    for line, confidence in zip(lines, confidences, strict=False):
        if confidence is not None and confidence < 0.75:
            noisy.append(line)
            continue
        ascii_letters = sum(
            character.isascii() and character.isalpha()
            for character in line
        )
        if ascii_letters >= 2:
            noisy.append(line)
    return noisy


def model_cache_state(model_name: str) -> str:
    model_dir = MODEL_CACHE_DIR / "official_models" / model_name
    if model_dir.is_dir():
        return "cached"
    return "not cached; first run may need model download"


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
            purpose="stress test missing upper-paragraph recovery",
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
        ),
        OcrTarget(
            name="difficult upper paragraph region",
            path=difficult_region_path,
            purpose="stress test isolated problematic region",
            expected_lines=KNOWN_UPPER_PARAGRAPH_LINES,
        ),
        OcrTarget(
            name="normal scanned clean page",
            path=normal_page_path,
            purpose="estimate ordinary full-page OCR quality",
            expected_lines=[],
        ),
        OcrTarget(
            name="mixed Chinese English finance page",
            path=mixed_page_path,
            purpose="probe mixed-language OCR behavior with chart/ticker text",
            expected_lines=[],
        ),
    ]


def model_configs() -> list[PaddleModelConfig]:
    settings = Settings()
    return [
        PaddleModelConfig(
            name="baseline mobile det + mobile rec",
            detection_model=settings.ocr_text_detection_model,
            recognition_model=settings.ocr_text_recognition_model,
            max_image_side=settings.ocr_max_image_side,
            purpose="current Echo baseline",
            expected_implication="fastest and most portable, but may miss faint/skewed text",
            deployment_note=(
                "smallest expected model footprint; most CPU-friendly; best fit for "
                "multiple concurrent users if quality is sufficient"
            ),
        ),
        PaddleModelConfig(
            name="server det + mobile rec",
            detection_model="PP-OCRv5_server_det",
            recognition_model=settings.ocr_text_recognition_model,
            max_image_side=settings.ocr_max_image_side,
            purpose="test whether text detection is the limiting step",
            expected_implication="may recover more boxes with higher CPU cost",
            deployment_note=(
                "larger detector download/cache; likely slower per page on CPU; "
                "concurrency may need job queueing or worker limits"
            ),
        ),
        PaddleModelConfig(
            name="mobile det + server rec",
            detection_model=settings.ocr_text_detection_model,
            recognition_model="PP-OCRv5_server_rec",
            max_image_side=settings.ocr_max_image_side,
            purpose="test whether recognition quality is the limiting step",
            expected_implication="may improve characters only for text already detected",
            deployment_note=(
                "larger recognizer download/cache; CPU cost depends on detected line "
                "count; helps only when detection already finds the line"
            ),
        ),
        PaddleModelConfig(
            name="server det + server rec",
            detection_model="PP-OCRv5_server_det",
            recognition_model="PP-OCRv5_server_rec",
            max_image_side=settings.ocr_max_image_side,
            purpose="test high-accuracy PP-OCRv5 pair",
            expected_implication="best accuracy candidate, highest CPU/model cost",
            deployment_note=(
                "largest expected footprint among tested PP-OCRv5 pairs; may be poor "
                "for synchronous CPU requests under concurrent load"
            ),
        ),
        PaddleModelConfig(
            name="baseline mobile at larger side",
            detection_model=settings.ocr_text_detection_model,
            recognition_model=settings.ocr_text_recognition_model,
            max_image_side=2600,
            purpose="test whether detector input resolution is the limiting step",
            expected_implication="may detect smaller/fainter text with extra CPU cost",
            deployment_note=(
                "no new model download beyond baseline, but higher image resolution "
                "increases CPU and memory per request"
            ),
        ),
    ]


def run_config_on_target(
    config: PaddleModelConfig,
    target: OcrTarget,
) -> PaddleRunResult:
    provider = PaddleOcrProvider(
        text_detection_model=config.detection_model,
        text_recognition_model=config.recognition_model,
        max_image_side=config.max_image_side,
        cache_path=MODEL_CACHE_DIR,
    )
    started_at = perf_counter()
    try:
        lines = provider._predict_lines(target.path)
    except Exception as error:  # noqa: BLE001 - experiment should report failures.
        return PaddleRunResult(
            config_name=config.name,
            target_name=target.name,
            detection_model=config.detection_model,
            recognition_model=config.recognition_model,
            max_image_side=config.max_image_side,
            purpose=config.purpose,
            expected_implication=config.expected_implication,
            deployment_note=config.deployment_note,
            processing_time_seconds=None,
            lines=[],
            confidences=[],
            unavailable_reason=repr(error),
        )
    elapsed = perf_counter() - started_at
    return PaddleRunResult(
        config_name=config.name,
        target_name=target.name,
        detection_model=config.detection_model,
        recognition_model=config.recognition_model,
        max_image_side=config.max_image_side,
        purpose=config.purpose,
        expected_implication=config.expected_implication,
        deployment_note=config.deployment_note,
        processing_time_seconds=elapsed,
        lines=[line.text for line in lines],
        confidences=[line.confidence for line in lines],
    )


def target_by_name(targets: list[OcrTarget], target_name: str) -> OcrTarget:
    return next(target for target in targets if target.name == target_name)


def print_model_inventory(configs: list[PaddleModelConfig]) -> None:
    print("== PaddleOCR model candidates ==")
    for config in configs:
        print(f"\n{config.name}")
        print(f"detection_model={config.detection_model}")
        print(f"detection_cache={model_cache_state(config.detection_model)}")
        print(f"recognition_model={config.recognition_model}")
        print(f"recognition_cache={model_cache_state(config.recognition_model)}")
        print(f"max_image_side={config.max_image_side}")
        print(f"purpose={config.purpose}")
        print(f"expected_implication={config.expected_implication}")
        print(f"deployment_note={config.deployment_note}")


def print_result(result: PaddleRunResult, targets: list[OcrTarget]) -> None:
    target = target_by_name(targets, result.target_name)
    text = "\n".join(result.lines)
    recovered = recovered_known_lines(text, target.expected_lines)
    missing = missing_known_lines(text, target.expected_lines)
    noise = likely_noise(result.lines, result.confidences)
    valid_confidences = [
        confidence for confidence in result.confidences if confidence is not None
    ]

    print(f"\n== {result.config_name}: {result.target_name} ==")
    print(f"target_purpose={target.purpose}")
    print(f"detection_model={result.detection_model}")
    print(f"recognition_model={result.recognition_model}")
    print(f"max_image_side={result.max_image_side}")
    print(f"config_purpose={result.purpose}")
    print(f"expected_implication={result.expected_implication}")
    print(f"deployment_note={result.deployment_note}")
    print(
        "multilingual_note=model choice is PaddleOCR-version and language dependent; "
        "Echo should compare Traditional Chinese, Simplified Chinese, English, "
        "Japanese/Korean availability, and mixed-language behavior before choosing "
        "a production strategy."
    )
    if result.unavailable_reason:
        print(f"unavailable_reason={result.unavailable_reason}")
        return
    print(f"processing_time_seconds={result.processing_time_seconds:.3f}")
    print(f"line_count={len(result.lines)}")
    if valid_confidences:
        print(f"average_confidence={fmean(valid_confidences):.3f}")
    else:
        print("average_confidence=n/a")
    print("recognized_text:")
    print(text or "(none)")
    print("recovered_known_lines:")
    if target.expected_lines:
        for line in recovered or ["none"]:
            print(f"- {line}")
    else:
        print("- not measured for this sample")
    print("missing_known_lines:")
    if target.expected_lines:
        for line in missing or ["none"]:
            print(f"- {line}")
    else:
        print("- not measured for this sample")
    print("likely_noise:")
    for line in noise or ["none"]:
        print(f"- {line}")


def print_summary_table(
    results: list[PaddleRunResult],
    targets: list[OcrTarget],
) -> None:
    print("\n== Summary table ==")
    print(
        "config,target,recovered_known,total_known,line_count,"
        "average_confidence,processing_time_seconds,unavailable"
    )
    for result in results:
        target = target_by_name(targets, result.target_name)
        text = "\n".join(result.lines)
        recovered_count = len(recovered_known_lines(text, target.expected_lines))
        total_known = len(target.expected_lines)
        valid_confidences = [
            confidence for confidence in result.confidences if confidence is not None
        ]
        average_confidence = (
            f"{fmean(valid_confidences):.3f}" if valid_confidences else "n/a"
        )
        processing_time = (
            f"{result.processing_time_seconds:.3f}"
            if result.processing_time_seconds is not None
            else "n/a"
        )
        unavailable = "yes" if result.unavailable_reason else "no"
        print(
            f"{result.config_name},{result.target_name},{recovered_count},"
            f"{total_known},{len(result.lines)},{average_confidence},"
            f"{processing_time},{unavailable}"
        )


def line_keys(lines: list[str]) -> set[str]:
    return {compact(line) for line in lines if compact(line)}


def result_for(
    results: list[PaddleRunResult],
    *,
    config_name: str,
    target_name: str,
) -> PaddleRunResult:
    return next(
        result
        for result in results
        if result.config_name == config_name and result.target_name == target_name
    )


def print_diagnostic_comparison(
    results: list[PaddleRunResult],
    targets: list[OcrTarget],
) -> None:
    baseline_name = "baseline mobile det + mobile rec"
    print("\n== Diagnostic comparison against baseline ==")
    for target in targets:
        baseline = result_for(
            results,
            config_name=baseline_name,
            target_name=target.name,
        )
        baseline_keys = line_keys(baseline.lines)
        baseline_text = "\n".join(baseline.lines)
        baseline_recovered = len(
            recovered_known_lines(baseline_text, target.expected_lines)
        )
        print(f"\nTarget: {target.name}")
        print(f"target_purpose={target.purpose}")
        for result in results:
            if result.target_name != target.name or result.config_name == baseline_name:
                continue
            current_keys = line_keys(result.lines)
            current_text = "\n".join(result.lines)
            recovered_count = len(
                recovered_known_lines(current_text, target.expected_lines)
            )
            new_line_count = len(current_keys - baseline_keys)
            dropped_line_count = len(baseline_keys - current_keys)
            noise_count = len(likely_noise(result.lines, result.confidences))
            processing_time = (
                f"{result.processing_time_seconds:.3f}s"
                if result.processing_time_seconds is not None
                else "n/a"
            )
            baseline_time = (
                f"{baseline.processing_time_seconds:.3f}s"
                if baseline.processing_time_seconds is not None
                else "n/a"
            )
            recall_delta = recovered_count - baseline_recovered
            print(f"- {result.config_name}")
            print(
                f"  detection_impact=new_lines_vs_baseline={new_line_count}; "
                f"dropped_lines_vs_baseline={dropped_line_count}; "
                "new useful known-line recovery suggests detector/resolution gain."
            )
            print(
                f"  recognition_impact=recovered_known_delta={recall_delta}; "
                f"noise_count={noise_count}; compare shared lines manually for "
                "character and punctuation quality."
            )
            print(
                f"  processing_impact={processing_time} vs baseline {baseline_time}; "
                f"deployment_note={result.deployment_note}"
            )


def print_echo_suitability_notes(results: list[PaddleRunResult]) -> None:
    successful = [
        result
        for result in results
        if result.unavailable_reason is None
        and result.processing_time_seconds is not None
    ]
    print("\n== Echo suitability rubric ==")
    print(
        "Use the summary table plus recognized text to choose the best practical "
        "balance, not just the highest confidence. Prefer the config that recovers "
        "missing meaningful text without adding noisy false text, keeps manual "
        "correction low before TTS, and remains practical for CPU workers."
    )
    print(
        "Deployment checks: record whether each model was already cached or needed "
        "download, whether CPU latency is acceptable for page batches, and whether "
        "multiple concurrent uploads require background jobs, worker concurrency "
        "limits, or separate OCR capacity."
    )
    if successful:
        fastest = min(successful, key=lambda result: result.processing_time_seconds or 0)
        slowest = max(successful, key=lambda result: result.processing_time_seconds or 0)
        print(
            f"fastest_observed={fastest.config_name} on {fastest.target_name} "
            f"({fastest.processing_time_seconds:.3f}s)"
        )
        print(
            f"slowest_observed={slowest.config_name} on {slowest.target_name} "
            f"({slowest.processing_time_seconds:.3f}s)"
        )


def main() -> None:
    configs = model_configs()
    targets = prepare_targets()
    print_model_inventory(configs)

    results: list[PaddleRunResult] = []
    for config in configs:
        for target in targets:
            result = run_config_on_target(config, target)
            results.append(result)
            print_result(result, targets)
    print_summary_table(results, targets)
    print_diagnostic_comparison(results, targets)
    print_echo_suitability_notes(results)
    print(f"\nSaved target images in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
