"""Compare OCR providers on one difficult Echo page.

Run from the repo root after approval with:
    ./backend/.venv/bin/python tmp/multi_ocr_provider_comparison/run_provider_comparison.py

This is an isolated experiment. It does not integrate any OCR provider into
Echo's production OCR pipeline.
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO
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
OUTPUT_DIR = REPO_ROOT / "tmp" / "multi_ocr_provider_comparison" / "outputs"
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


@dataclass(frozen=True)
class OcrRunResult:
    provider: str
    target: str
    configuration: str
    language_support: str
    linux_portability: str
    processing_time_seconds: float | None
    lines: list[str]
    confidences: list[float | None]
    unavailable_reason: str | None = None


_PADDLE_PROVIDER: PaddleOcrProvider | None = None
_EASYOCR_READER = None


def compact(text: str) -> str:
    return "".join(text.split()).replace(",", "，").replace("·", "，")


def recovered_known_lines(text: str, expected_lines: list[str]) -> list[str]:
    compact_text = compact(text)
    return [
        line
        for line in expected_lines
        if compact(line) in compact_text
    ]


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


def run_paddle(target: OcrTarget) -> OcrRunResult:
    global _PADDLE_PROVIDER
    settings = Settings()
    if _PADDLE_PROVIDER is None:
        _PADDLE_PROVIDER = PaddleOcrProvider(
            text_detection_model=settings.ocr_text_detection_model,
            text_recognition_model=settings.ocr_text_recognition_model,
            max_image_side=settings.ocr_max_image_side,
            cache_path=BACKEND_ROOT / "data" / "models" / "paddlex",
        )
    started_at = perf_counter()
    lines = _PADDLE_PROVIDER._predict_lines(target.path)
    elapsed = perf_counter() - started_at
    return OcrRunResult(
        provider="PaddleOCR",
        target=target.name,
        configuration=(
            f"det={settings.ocr_text_detection_model}; "
            f"rec={settings.ocr_text_recognition_model}; "
            f"max_image_side={settings.ocr_max_image_side}"
        ),
        language_support="model-dependent; current config uses PaddleOCR selected models",
        linux_portability="portable in backend venv with pinned PaddleOCR/PaddlePaddle CPU packages",
        processing_time_seconds=elapsed,
        lines=[line.text for line in lines],
        confidences=[line.confidence for line in lines],
    )


def run_tesseract_text(target: OcrTarget) -> str:
    return subprocess.run(
        [
            "tesseract",
            str(target.path),
            "stdout",
            "-l",
            "chi_tra+eng",
            "--psm",
            "6",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_tesseract_tsv(target: OcrTarget) -> str:
    return subprocess.run(
        [
            "tesseract",
            str(target.path),
            "stdout",
            "-l",
            "chi_tra+eng",
            "--psm",
            "6",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def parse_tesseract_tsv(tsv_text: str) -> tuple[list[str], list[float | None]]:
    reader = csv.DictReader(StringIO(tsv_text), delimiter="\t")
    grouped: dict[tuple[str, str, str], list[tuple[str, float | None]]] = {}
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        confidence_text = row.get("conf") or "-1"
        confidence = float(confidence_text) / 100 if confidence_text != "-1" else None
        grouped.setdefault(key, []).append((text, confidence))

    lines: list[str] = []
    confidences: list[float | None] = []
    for parts in grouped.values():
        line = "".join(part for part, _ in parts)
        valid_confidences = [
            confidence for _, confidence in parts if confidence is not None
        ]
        lines.append(line)
        confidences.append(fmean(valid_confidences) if valid_confidences else None)
    return lines, confidences


def run_tesseract(target: OcrTarget) -> OcrRunResult:
    if shutil.which("tesseract") is None:
        return unavailable(
            "Tesseract OCR",
            target,
            "tesseract executable not found",
            "language data dependent; planned test uses chi_tra+eng",
            "portable if system package and traineddata files are installed",
        )

    started_at = perf_counter()
    text_output = run_tesseract_text(target)
    tsv_output = run_tesseract_tsv(target)
    elapsed = perf_counter() - started_at
    lines, confidences = parse_tesseract_tsv(tsv_output)
    if not lines:
        lines = [line for line in text_output.splitlines() if line.strip()]
        confidences = [None for _ in lines]
    return OcrRunResult(
        provider="Tesseract OCR",
        target=target.name,
        configuration="language=chi_tra+eng; page_segmentation_mode=6",
        language_support="language data dependent; broad coverage but quality varies by script",
        linux_portability="portable through apt/apk packages plus traineddata files",
        processing_time_seconds=elapsed,
        lines=lines,
        confidences=confidences,
    )


def run_easyocr(target: OcrTarget) -> OcrRunResult:
    global _EASYOCR_READER
    if importlib.util.find_spec("easyocr") is None:
        return unavailable(
            "EasyOCR",
            target,
            "easyocr is not installed in the backend virtualenv",
            "multilingual reader configured per language list; Traditional Chinese support needs validation",
            "portable on Linux, but adds PyTorch model/runtime dependency",
        )

    import easyocr  # noqa: PLC0415

    started_at = perf_counter()
    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["ch_tra", "en"], gpu=False)
    raw_results = _EASYOCR_READER.readtext(
        str(target.path),
        detail=1,
        paragraph=False,
    )
    elapsed = perf_counter() - started_at
    return OcrRunResult(
        provider="EasyOCR",
        target=target.name,
        configuration="languages=ch_tra,en; gpu=false",
        language_support="multilingual reader by configured language list",
        linux_portability="portable with PyTorch CPU packages, but heavier than PaddleOCR/Tesseract",
        processing_time_seconds=elapsed,
        lines=[
            str(result[1]).strip()
            for result in raw_results
            if str(result[1]).strip()
        ],
        confidences=[
            float(result[2])
            for result in raw_results
            if str(result[1]).strip()
        ],
    )


def unavailable(
    provider: str,
    target: OcrTarget,
    reason: str,
    language_support: str,
    linux_portability: str,
) -> OcrRunResult:
    return OcrRunResult(
        provider=provider,
        target=target.name,
        configuration="unavailable",
        language_support=language_support,
        linux_portability=linux_portability,
        processing_time_seconds=None,
        lines=[],
        confidences=[],
        unavailable_reason=reason,
    )


def print_result(result: OcrRunResult) -> None:
    text = "\n".join(result.lines)
    expected_lines = next(
        target.expected_lines
        for target in PREPARED_TARGETS
        if target.name == result.target
    )
    recovered = recovered_known_lines(text, expected_lines)
    missing = missing_known_lines(text, expected_lines)
    noise = likely_noise(result.lines, result.confidences)
    valid_confidences = [
        confidence for confidence in result.confidences if confidence is not None
    ]

    print(f"\n== {result.provider}: {result.target} ==")
    print(f"target_purpose={target_purpose(result.target)}")
    print(f"configuration={result.configuration}")
    print(f"language_support={result.language_support}")
    print(f"linux_portability={result.linux_portability}")
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
    if expected_lines:
        for line in recovered or ["none"]:
            print(f"- {line}")
    else:
        print("- not measured for this sample")
    print("missing_known_lines:")
    if expected_lines:
        for line in missing or ["none"]:
            print(f"- {line}")
    else:
        print("- not measured for this sample")
    print("likely_noise:")
    for line in noise or ["none"]:
        print(f"- {line}")


def target_purpose(target_name: str) -> str:
    return next(
        target.purpose
        for target in PREPARED_TARGETS
        if target.name == target_name
    )


PREPARED_TARGETS: list[OcrTarget] = []


def main() -> None:
    PREPARED_TARGETS.extend(prepare_targets())
    providers = [run_paddle, run_tesseract, run_easyocr]
    for target in PREPARED_TARGETS:
        for provider in providers:
            print_result(provider(target))
    print(f"\nSaved target images in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
