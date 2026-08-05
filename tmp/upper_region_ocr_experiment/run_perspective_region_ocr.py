"""Isolated perspective-correction OCR experiment for the upper paragraph.

Compares the original crop, a manually perspective-corrected crop, and one mild
grayscale/contrast variant using Echo's current PaddleOCR configuration.
Run from the repo root with:
    ./backend/.venv/bin/python tmp/upper_region_ocr_experiment/run_perspective_region_ocr.py

This script is experimental only and does not modify Echo's production OCR pipeline.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageEnhance, ImageOps


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
OUTPUT_DIR = REPO_ROOT / "tmp" / "upper_region_ocr_experiment" / "outputs_perspective"

# Same original-resolution crop used in the first experiment.
UPPER_REGION_BOX = (50, 190, 960, 520)

# Manual quadrilateral around the same upper region after accounting for the
# visible page/text skew. Output dimensions intentionally match the original crop.
PERSPECTIVE_QUAD = (
    40,
    24,
    0,
    330,
    910,
    330,
    890,
    0,
)

KNOWN_MISSING_LINES = [
    "業、醫療設備、金融業、核心科技或必需品消費股等。",
    "期權負責短期保障、鎖定收入和捕捉機會。",
    "即使面對戰爭陰霾或地緣衝突也不用恐慌賣出，而是從容調整。",
    "在動盪的2025年中，許多零售投資者正是因為這種組合，資產不跌",
]


@dataclass(frozen=True)
class Variant:
    name: str
    image: Image.Image
    path: Path


def build_provider() -> PaddleOcrProvider:
    settings = Settings()
    return PaddleOcrProvider(
        text_detection_model=settings.ocr_text_detection_model,
        text_recognition_model=settings.ocr_text_recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=BACKEND_ROOT / "data" / "models" / "paddlex",
    )


def save_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def recognized_text(lines) -> str:
    return "\n".join(line.text for line in lines)


def recovered_known_lines(text: str) -> list[str]:
    recovered: list[str] = []
    compact_text = "".join(text.split())
    for line in KNOWN_MISSING_LINES:
        compact_line = "".join(line.split())
        if compact_line in compact_text:
            recovered.append(line)
    return recovered


def print_variant_result(name: str, elapsed: float, lines) -> None:
    text = recognized_text(lines)
    recovered = recovered_known_lines(text)
    noisy = [
        line.text
        for line in lines
        if line.confidence < 0.75 or any(char.isascii() and char.isalpha() for char in line.text)
    ]

    print(f"\n== {name} ==")
    print(f"processing_time_seconds={elapsed:.3f}")
    print(f"ocr_line_count={len(lines)}")
    print("recognized_text:")
    if text:
        print(text)
    else:
        print("(none)")
    print("confidences:")
    for index, line in enumerate(lines):
        print(f"{index:02d}: {line.confidence:.2f} {line.text}")
    print("known_missing_lines_recovered:")
    if recovered:
        for line in recovered:
            print(f"- {line}")
    else:
        print("- none")
    print("obvious_ocr_noise:")
    if noisy:
        for line in noisy:
            print(f"- {line}")
    else:
        print("- none")


def main() -> None:
    provider = build_provider()
    provider._get_pipeline()

    with Image.open(IMAGE_PATH) as source:
        page = ImageOps.exif_transpose(source).convert("RGB")
        original_crop = page.crop(UPPER_REGION_BOX)

    width, height = original_crop.size
    corrected = original_crop.transform(
        (width, height),
        Image.Transform.QUAD,
        PERSPECTIVE_QUAD,
        Image.Resampling.BICUBIC,
    )

    normalized = ImageOps.grayscale(corrected)
    normalized = ImageOps.autocontrast(normalized)
    normalized = ImageEnhance.Contrast(normalized).enhance(1.20)

    variants = [
        Variant(
            name="original-resolution manual upper-region crop",
            image=original_crop,
            path=OUTPUT_DIR / "01-original-resolution-upper-region.png",
        ),
        Variant(
            name="perspective-corrected upper-region crop",
            image=corrected,
            path=OUTPUT_DIR / "02-perspective-corrected-upper-region.png",
        ),
        Variant(
            name="perspective-corrected mild grayscale contrast",
            image=normalized,
            path=OUTPUT_DIR / "03-perspective-corrected-grayscale-contrast.png",
        ),
    ]

    for variant in variants:
        save_image(variant.path, variant.image)
        started_at = perf_counter()
        lines = provider._predict_lines(variant.path)
        elapsed = perf_counter() - started_at
        print_variant_result(variant.name, elapsed, lines)

    print(f"\nSaved outputs in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
