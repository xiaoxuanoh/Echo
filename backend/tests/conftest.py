from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def storage_path(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def client(storage_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        max_pdf_size_mb=1,
        max_image_size_mb=1,
        max_image_upload_count=3,
        max_image_pixels=10_000_000,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def make_pdf(page_texts: list[str | None]) -> bytes:
    """Create a small dependency-free PDF fixture with text or blank pages."""

    page_count = len(page_texts)
    page_ids = [4 + index for index in range(page_count)]
    content_ids = [4 + page_count + index for index in range(page_count)]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    for page_id, content_id in zip(page_ids, content_ids, strict=True):
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )

    for text in page_texts:
        stream = (
            f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
            if text is not None
            else b""
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)
