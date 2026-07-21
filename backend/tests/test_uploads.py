import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import make_pdf


def image_bytes(
    size: tuple[int, int],
    image_format: str = "PNG",
    *,
    exif_orientation: int | None = None,
) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", size, color="#d7e3ed")
    exif = image.getexif()
    if exif_orientation is not None:
        exif[274] = exif_orientation
    image.save(output, format=image_format, exif=exif)
    return output.getvalue()


def test_uploads_and_classifies_pdf(client: TestClient, storage_path: Path) -> None:
    response = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "mixed-book.pdf",
                make_pdf(["A page with selectable embedded text.", None]),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["original_filename"] == "mixed-book.pdf"
    assert result["total_pages"] == 2
    assert result["classification"] == "mixed"
    assert [page["classification"] for page in result["pages"]] == [
        "embedded_text",
        "requires_ocr",
    ]
    book_directory = storage_path / result["book_id"]
    assert (book_directory / "source.pdf").exists()
    assert not (book_directory / "pages" / "page-0001.png").exists()
    assert (book_directory / "pages" / "page-0002.png").exists()

    metadata = json.loads((book_directory / "book.json").read_text())
    assert metadata["source_type"] == "pdf"
    assert metadata["source_storage_path"] == "source.pdf"
    assert [page["page_number"] for page in metadata["pages"]] == [1, 2]
    assert metadata["pages"][0]["extraction_method"] == "embedded_text"
    assert "selectable embedded text" in metadata["pages"][0]["extracted_text"]
    assert metadata["pages"][0]["processing_status"] == "completed"
    assert metadata["pages"][1]["extraction_method"] == "ocr"
    assert metadata["pages"][1]["processed_image_path"] == "pages/page-0002.png"
    assert metadata["pages"][1]["processing_status"] == "pending"


def test_rejects_invalid_and_oversized_pdf(client: TestClient) -> None:
    invalid = client.post(
        "/api/books/pdf",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    oversized = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "large.pdf",
                b"%PDF-" + b"0" * (1024 * 1024),
                "application/pdf",
            )
        },
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_pdf"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "file_too_large"


def test_preserves_image_order_and_applies_rotation(
    client: TestClient,
    storage_path: Path,
) -> None:
    response = client.post(
        "/api/books/images",
        files=[
            ("files", ("second.png", image_bytes((12, 20)), "image/png")),
            ("files", ("first.jpg", image_bytes((8, 10), "JPEG"), "image/jpeg")),
        ],
        data={"rotations": "[90, 0]"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["ordered_image_filenames"] == ["second.png", "first.jpg"]
    assert [page["rotation_degrees"] for page in result["pages"]] == [90, 0]
    normalized_path = storage_path / result["book_id"] / "pages" / "page-0001.png"
    with Image.open(normalized_path) as normalized:
        assert normalized.size == (20, 12)

    metadata_path = storage_path / result["book_id"] / "book.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["source_type"] == "images"
    assert [page["original_filename"] for page in metadata["pages"]] == [
        "second.png",
        "first.jpg",
    ]
    assert [page["page_number"] for page in metadata["pages"]] == [1, 2]
    assert all(page["extraction_method"] == "ocr" for page in metadata["pages"])
    assert all(page["processing_status"] == "pending" for page in metadata["pages"])
    assert metadata["pages"][0]["original_image_path"].startswith("originals/")
    assert metadata["pages"][0]["processed_image_path"] == "pages/page-0001.png"


def test_corrects_exif_orientation_before_user_rotation(tmp_path: Path) -> None:
    from app.services.image_processing import ImageProcessingService

    source = tmp_path / "rotated.jpg"
    destination = tmp_path / "normalized.png"
    source.write_bytes(image_bytes((10, 20), "JPEG", exif_orientation=6))

    ImageProcessingService(max_pixels=10_000).normalize_image(source, destination, 0)

    with Image.open(destination) as normalized:
        assert normalized.size == (20, 10)


def test_rejects_invalid_images_rotations_and_count(client: TestClient) -> None:
    invalid_image = client.post(
        "/api/books/images",
        files=[("files", ("page.png", b"not an image", "image/png"))],
        data={"rotations": "[0]"},
    )
    invalid_rotation = client.post(
        "/api/books/images",
        files=[("files", ("page.png", image_bytes((5, 5)), "image/png"))],
        data={"rotations": "[45]"},
    )
    oversized_file = client.post(
        "/api/books/images",
        files=[
            (
                "files",
                ("large.png", image_bytes((5, 5)) + b"0" * (1024 * 1024), "image/png"),
            )
        ],
        data={"rotations": "[0]"},
    )
    too_many_pixels = client.post(
        "/api/books/images",
        files=[
            ("files", ("wide.png", image_bytes((4001, 2500)), "image/png")),
        ],
        data={"rotations": "[0]"},
    )
    too_many = client.post(
        "/api/books/images",
        files=[
            ("files", (f"page-{index}.png", image_bytes((5, 5)), "image/png"))
            for index in range(4)
        ],
        data={"rotations": "[0, 0, 0, 0]"},
    )

    assert invalid_image.json()["error"]["code"] == "invalid_image"
    assert invalid_rotation.json()["error"]["code"] == "invalid_rotation"
    assert oversized_file.status_code == 413
    assert oversized_file.json()["error"]["code"] == "file_too_large"
    assert too_many_pixels.status_code == 413
    assert too_many_pixels.json()["error"]["code"] == "image_too_large"
    assert too_many.status_code == 413
    assert too_many.json()["error"]["code"] == "too_many_images"
