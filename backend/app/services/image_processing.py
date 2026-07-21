from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import EchoError


AllowedRotation = Literal[0, 90, 180, 270]


@dataclass(frozen=True)
class ImageDetails:
    format: Literal["JPEG", "PNG"]
    width: int
    height: int


class ImageProcessingService:
    """Validates and normalizes uploaded page photographs."""

    allowed_rotations = {0, 90, 180, 270}
    allowed_formats = {"JPEG", "PNG"}

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
                normalized.save(destination, format="PNG", optimize=True)
        except EchoError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise EchoError(
                "image_processing_failed",
                "Echo could not prepare one of the page images.",
            ) from error

    def save_rendered_page(self, image: Image.Image, destination: Path) -> None:
        """Save a PDF-rendered page in the same stable format as page photos."""

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
            normalized.save(destination, format="PNG", optimize=True)
        except OSError as error:
            raise EchoError(
                "image_processing_failed",
                "Echo could not prepare one of the PDF pages.",
            ) from error
