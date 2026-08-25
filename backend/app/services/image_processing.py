from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import EchoError


AllowedRotation = Literal[0, 90, 180, 270]
CropRectangle = tuple[float, float, float, float]


@dataclass(frozen=True)
class ImageDetails:
    format: Literal["JPEG", "PNG"]
    width: int
    height: int


class ImageProcessingService:
    """Validates and normalizes uploaded page photographs."""

    allowed_rotations = {0, 90, 180, 270}
    allowed_formats = {"JPEG", "PNG"}
    crop_scan_max_side = 512
    paper_min_value = 160
    paper_max_saturation = 65
    paper_axis_coverage = 0.30
    crop_padding_ratio = 0.04
    min_crop_axis_ratio = 0.35
    min_crop_area_ratio = 0.40

    def __init__(self, max_pixels: int) -> None:
        self.max_pixels = max_pixels

    def validate_image(self, path: Path) -> ImageDetails:
        try:
            with Image.open(path) as image:
                image_format = image.format
                width, height = image.size
                if image_format not in self.allowed_formats:
                    raise EchoError(
                        "unsupported_image",
                        "Only JPG, JPEG, and PNG page images are supported.",
                    )
                if width * height > self.max_pixels:
                    raise EchoError(
                        "image_too_large",
                        "This image has too many pixels to process safely.",
                        status_code=413,
                        details={"max_pixels": self.max_pixels},
                    )
                image.verify()
        except EchoError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise EchoError(
                "invalid_image",
                "One of the selected files is not a readable JPG or PNG image.",
            ) from error

        return ImageDetails(format=image_format, width=width, height=height)  # type: ignore[arg-type]

    def normalize_image(
        self,
        source: Path,
        destination: Path,
        rotation_degrees: int,
        crop_rectangle: CropRectangle | None = None,
    ) -> None:
        if rotation_degrees not in self.allowed_rotations:
            raise EchoError(
                "invalid_rotation",
                "Page rotation must be 0, 90, 180, or 270 degrees.",
            )

        self.validate_image(source)
        try:
            with Image.open(source) as image:
                normalized = ImageOps.exif_transpose(image)
                if rotation_degrees:
                    normalized = normalized.rotate(-rotation_degrees, expand=True)
                if normalized.mode not in {"RGB", "L"}:
                    normalized = normalized.convert("RGB")
                if crop_rectangle is not None:
                    normalized = self._crop_rectangle(normalized, crop_rectangle)
                normalized.save(destination, format="PNG", optimize=True)
        except EchoError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise EchoError(
                "image_processing_failed",
                "Echo could not prepare one of the page images.",
            ) from error

    def _crop_likely_page_area(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        if width < 100 or height < 100:
            return image

        scale = min(1.0, self.crop_scan_max_side / max(width, height))
        scan_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        scan = image.convert("RGB").resize(scan_size, Image.Resampling.BILINEAR)
        hsv = scan.convert("HSV")
        scan_width, scan_height = scan.size

        paper_pixels: list[list[bool]] = []
        for y in range(scan_height):
            row: list[bool] = []
            for x in range(scan_width):
                _, saturation, value = hsv.getpixel((x, y))
                row.append(
                    value >= self.paper_min_value
                    and saturation <= self.paper_max_saturation
                )
            paper_pixels.append(row)

        column_counts = [
            sum(paper_pixels[y][x] for y in range(scan_height))
            for x in range(scan_width)
        ]
        row_counts = [
            sum(paper_pixels[y][x] for x in range(scan_width))
            for y in range(scan_height)
        ]
        x_segment = self._largest_dense_segment(
            column_counts,
            threshold=scan_height * self.paper_axis_coverage,
            min_length=scan_width * self.min_crop_axis_ratio,
        )
        y_segment = self._largest_dense_segment(
            row_counts,
            threshold=scan_width * self.paper_axis_coverage,
            min_length=scan_height * self.min_crop_axis_ratio,
        )
        if x_segment is None or y_segment is None:
            return image

        left = max(0, int(x_segment[0] / scale) - round(width * self.crop_padding_ratio))
        right = min(
            width,
            int((x_segment[1] + 1) / scale) + round(width * self.crop_padding_ratio),
        )
        top = max(0, int(y_segment[0] / scale) - round(height * self.crop_padding_ratio))
        bottom = min(
            height,
            int((y_segment[1] + 1) / scale) + round(height * self.crop_padding_ratio),
        )
        crop_width = right - left
        crop_height = bottom - top
        crop_area = crop_width * crop_height
        image_area = width * height
        if crop_area < image_area * self.min_crop_area_ratio:
            return image
        if crop_width >= width * 0.98 and crop_height >= height * 0.98:
            return image

        return image.crop((left, top, right, bottom))

    def _crop_rectangle(
        self,
        image: Image.Image,
        crop_rectangle: CropRectangle,
    ) -> Image.Image:
        crop_left, crop_top, crop_right, crop_bottom = crop_rectangle
        if (
            crop_left < 0
            or crop_top < 0
            or crop_right > 1
            or crop_bottom > 1
            or crop_left >= crop_right
            or crop_top >= crop_bottom
        ):
            raise EchoError(
                "invalid_crop",
                "The crop area must stay inside the page image.",
            )

        width, height = image.size
        left = int(width * crop_left)
        top = int(height * crop_top)
        right = max(left + 1, int(width * crop_right))
        bottom = max(top + 1, int(height * crop_bottom))
        return image.crop((left, top, min(width, right), min(height, bottom)))

    @staticmethod
    def _largest_dense_segment(
        counts: list[int],
        *,
        threshold: float,
        min_length: float,
    ) -> tuple[int, int] | None:
        best: tuple[int, int] | None = None
        start: int | None = None
        for index, count in enumerate(counts):
            if count > threshold and start is None:
                start = index
            is_last = index == len(counts) - 1
            if start is not None and (count <= threshold or is_last):
                end = index if is_last and count > threshold else index - 1
                if end - start + 1 >= min_length:
                    if best is None or end - start > best[1] - best[0]:
                        best = (start, end)
                start = None
        return best

    def save_rendered_page(
        self,
        image: Image.Image,
        destination: Path,
        crop_rectangle: CropRectangle | None = None,
        rotation_degrees: int = 0,
    ) -> None:
        """Save a PDF-rendered page in the same stable format as page photos."""

        if rotation_degrees not in self.allowed_rotations:
            raise EchoError(
                "invalid_rotation",
                "Page rotation must be 0, 90, 180, or 270 degrees.",
                status_code=422,
            )
        if image.width * image.height > self.max_pixels:
            raise EchoError(
                "image_too_large",
                "A rendered PDF page has too many pixels to process safely.",
                status_code=413,
                details={"max_pixels": self.max_pixels},
            )
        try:
            normalized = image
            if normalized.mode not in {"RGB", "L"}:
                normalized = normalized.convert("RGB")
            if rotation_degrees:
                normalized = normalized.rotate(-rotation_degrees, expand=True)
            if crop_rectangle is not None:
                normalized = self._crop_rectangle(normalized, crop_rectangle)
            normalized.save(destination, format="PNG", optimize=True)
        except OSError as error:
            raise EchoError(
                "image_processing_failed",
                "Echo could not prepare one of the PDF pages.",
            ) from error
