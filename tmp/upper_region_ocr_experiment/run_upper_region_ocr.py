"""Isolated OCR experiment for the photographed page upper paragraph.

Compares full-page PaddleOCR with manually cropped upper-region variants.
Run from the repo root with:
    ./backend/.venv/bin/python tmp/upper_region_ocr_experiment/run_upper_region_ocr.py

This script is experimental only and does not modify Echo's production OCR pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
OUTPUT_DIR = REPO_ROOT / "tmp" / "upper_region_ocr_experiment" / "outputs"

# Manual upper paragraph area from the inspected page image.
UPPER_REGION_BOX = (50, 190, 960, 520)


def print_lines(label: str, lines) -> None:
    print(f"\n== {label} ==")
    print(f"line_count={len(lines)}")
    for index, line in enumerate(lines):
        print(
            f"{index:02d} y={line.y_min} x={line.x_min}-{line.x_max} "
            f"conf={line.confidence:.2f} {line.text}"
        )


def save_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def main() -> None:
    settings = Settings()
    provider = PaddleOcrProvider(
        text_detection_model=settings.ocr_text_detection_model,
        text_recognition_model=settings.ocr_text_recognition_model,
        max_image_side=settings.ocr_max_image_side,
        cache_path=BACKEND_ROOT / "data" / "models" / "paddlex",
    )

    full_lines = provider._predict_lines(IMAGE_PATH)
    print_lines("current full-page OCR", full_lines)

    with Image.open(IMAGE_PATH) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        upper_crop = image.crop(UPPER_REGION_BOX)

    manual_crop_path = OUTPUT_DIR / "upper-region-manual-crop.png"
    save_image(manual_crop_path, upper_crop)
    manual_lines = provider._predict_lines(manual_crop_path)
    print_lines("manual isolated upper-region crop", manual_lines)

    enlarged = upper_crop.resize(
        (upper_crop.width * 3, upper_crop.height * 3),
        Image.Resampling.LANCZOS,
    )
    enlarged_path = OUTPUT_DIR / "upper-region-enlarged-3x.png"
    save_image(enlarged_path, enlarged)
    enlarged_lines = provider._predict_lines(enlarged_path)
    print_lines("enlarged upper-region crop", enlarged_lines)

    enhanced = ImageOps.autocontrast(upper_crop)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.35)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.10)
    enhanced = enhanced.resize(
        (enhanced.width * 3, enhanced.height * 3),
        Image.Resampling.LANCZOS,
    )
    enhanced_path = OUTPUT_DIR / "upper-region-enhanced-3x.png"
    save_image(enhanced_path, enhanced)
    enhanced_lines = provider._predict_lines(enhanced_path)
    print_lines("conservative enhanced upper-region crop", enhanced_lines)

    print(f"\nSaved crops in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
