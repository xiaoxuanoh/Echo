"""Isolated OCR provider comparison for the photographed page upper paragraph.

Recreates the original-resolution upper-region crop, then compares Echo's current
PaddleOCR configuration with local Tesseract using chi_tra for this test page.
Run from the repo root with:
    ./backend/.venv/bin/python tmp/upper_region_ocr_experiment/run_tesseract_comparison.py

This script treats Tesseract as a multilingual comparison engine only and does
not integrate it into Echo's production OCR pipeline.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from statistics import mean
from time import perf_counter

from PIL import Image, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.services.ocr import PaddleOcrProvider  # noqa: E402


IMAGE_PATH = (
    BACKEND_ROOT
    / "data"
    / "11ab953f-a194-42ed-b165-6349be45002c"
    / "pages"
    / "page-0001.png"
)
OUTPUT_DIR = REPO_ROOT / "tmp" / "upper_region_ocr_experiment" / "outputs_tesseract"
CROP_PATH = (
    OUTPUT_DIR / "original-resolution-upper-region.png"
)
UPPER_REGION_BOX = (50, 190, 960, 520)

KNOWN_MISSING_LINES = [
    "業、醫療設備、金融業、核心科技或必需品消費股等。",
    "期權負責短期保障、鎖定收入和捕捉機會。",
    "即使面對戰爭陰霾或地緣衝突也不用恐慌賣出，而是從容調整。",
    "在動盪的2025年中，許多零售投資者正是因為這種組合，資產不跌",
]


@dataclass(frozen=True)
class OcrComparisonResult:
    provider: str
    configuration: str
    processing_time_seconds: float
    lines: list[str]
    confidences: list[float | None]


def compact(text: str) -> str:
    return "".join(text.split()).replace("·", "，").replace(",", "，")


def recovered_known_lines(text: str) -> list[str]:
    compact_text = compact(text)
    return [line for line in KNOWN_MISSING_LINES if compact(line) in compact_text]


def obvious_noise(lines: list[str], confidences: list[float | None]) -> list[str]:
    noise: list[str] = []
    for line, confidence in zip(lines, confidences, strict=False):
        if confidence is not None and confidence < 70:
            noise.append(line)
            continue
        ascii_letters = sum(char.isascii() and char.isalpha() for char in line)
        if ascii_letters >= 2:
            noise.append(line)
    return noise


def print_result(result: OcrComparisonResult) -> None:
    text = "\n".join(result.lines)
    recovered = recovered_known_lines(text)
    noise = obvious_noise(result.lines, result.confidences)

    print(f"\n== {result.provider} ==")
    print(f"configuration={result.configuration}")
    print(f"processing_time_seconds={result.processing_time_seconds:.3f}")
    print(f"line_count={len(result.lines)}")
    print("recognized_text:")
    if text:
        print(text)
    else:
        print("(none)")
    print("confidences:")
    if result.lines:
        for index, (line, confidence) in enumerate(
            zip(result.lines, result.confidences, strict=False)
        ):
            rendered = "n/a" if confidence is None else f"{confidence:.2f}"
            print(f"{index:02d}: {rendered} {line}")
    else:
        print("(none)")
    print("known_missing_lines_recovered:")
    if recovered:
        for line in recovered:
            print(f"- {line}")
    else:
        print("- none")
    print("obvious_ocr_noise:")
    if noise:
        for line in noise:
            print(f"- {line}")
    else:
        print("- none")


def prepare_crop() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(IMAGE_PATH) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        upper_crop = image.crop(UPPER_REGION_BOX)
    upper_crop.save(CROP_PATH, format="PNG")


def run_paddle() -> OcrComparisonResult:
    settings = Settings()
    provider = PaddleOcrProvider(
        text_detection_model=settings.ocr_text_detection_model,
        text_recognition_model=settings.ocr_text_recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=BACKEND_ROOT / "data" / "models" / "paddlex",
    )
    started_at = perf_counter()
    lines = provider._predict_lines(CROP_PATH)
    elapsed = perf_counter() - started_at
    return OcrComparisonResult(
        provider="PaddleOCR",
        configuration=(
            f"det={settings.ocr_text_detection_model}; "
            f"rec={settings.ocr_text_recognition_model}; "
            f"max_image_side={settings.ocr_max_image_side}"
        ),
        processing_time_seconds=elapsed,
        lines=[line.text for line in lines],
        confidences=[line.confidence * 100 for line in lines],
    )


def run_tesseract_text() -> str:
    return subprocess.run(
        ["tesseract", str(CROP_PATH), "stdout", "-l", "chi_tra", "--psm", "6"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_tesseract_tsv() -> str:
    return subprocess.run(
        [
            "tesseract",
            str(CROP_PATH),
            "stdout",
            "-l",
            "chi_tra",
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
        confidence = float(confidence_text) if confidence_text != "-1" else None
        grouped.setdefault(key, []).append((text, confidence))

    lines: list[str] = []
    confidences: list[float | None] = []
    for parts in grouped.values():
        line = "".join(part for part, _ in parts)
        valid_confidences = [
            confidence for _, confidence in parts if confidence is not None
        ]
        lines.append(line)
        confidences.append(mean(valid_confidences) if valid_confidences else None)
    return lines, confidences


def run_tesseract() -> OcrComparisonResult:
    started_at = perf_counter()
    text_output = run_tesseract_text()
    tsv_output = run_tesseract_tsv()
    elapsed = perf_counter() - started_at
    lines, confidences = parse_tesseract_tsv(tsv_output)
    if not lines:
        lines = [line for line in text_output.splitlines() if line.strip()]
        confidences = [None for _ in lines]
    return OcrComparisonResult(
        provider="Tesseract OCR",
        configuration="language=chi_tra; page_segmentation_mode=6",
        processing_time_seconds=elapsed,
        lines=lines,
        confidences=confidences,
    )


def main() -> None:
    prepare_crop()
    print(f"crop={CROP_PATH}")
    for result in [run_paddle(), run_tesseract()]:
        print_result(result)


if __name__ == "__main__":
    main()
