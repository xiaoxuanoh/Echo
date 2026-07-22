from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.books import BookPageRecord
from app.services.book_metadata import LocalBookMetadataService
from app.services.text_segmentation import TextSegmentationService
from tests.conftest import make_pdf


def test_segments_text_without_exceeding_limit() -> None:
    now = datetime.now(UTC)
    book_id = uuid4()
    page_id = uuid4()
    page = BookPageRecord(
        id=page_id,
        book_id=book_id,
        page_number=1,
        extraction_method="embedded_text",
        extracted_text="First sentence. Second sentence. Third sentence.",
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )
    service = TextSegmentationService(max_characters=20)

    segments = service.segment_pages([page])

    assert [segment.page_number for segment in segments] == [1, 1, 1]
    assert all(len(segment.source_text) <= 20 for segment in segments)
    assert " ".join(segment.source_text for segment in segments).replace(
        "  ", " "
    ) == "First sentence. Second sentence. Third sentence."


def test_prepares_mock_audio_for_text_ready_book(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "digital.pdf",
                make_pdf(["This page is ready for mock audio."]),
                "application/pdf",
            )
        },
    ).json()
    client.post(f"/api/books/{upload['book_id']}/process-text")

    accepted = client.post(f"/api/books/{upload['book_id']}/prepare-audio")
    detail = client.get(f"/api/books/{upload['book_id']}")
    audio = client.get(f"/api/books/{upload['book_id']}/audio")

    assert accepted.status_code == 202
    assert detail.json()["processing_status"] == "ready"
    assert detail.json()["audio_segment_count"] == 1
    assert audio.status_code == 200
    assert audio.json()["processing_status"] == "ready"
    assert audio.json()["segments"][0]["processing_status"] == "completed"
    assert audio.json()["segments"][0]["audio_url"].endswith("/audio/1/file")

    saved = LocalBookMetadataService().load(storage_path / upload["book_id"])
    assert saved.status == "ready"
    assert saved.audio_segments[0].audio_storage_path == "audio/segment-0001.wav"
    assert (storage_path / upload["book_id"] / "audio" / "segment-0001.wav").exists()


def test_returns_mock_audio_file(client: TestClient) -> None:
    upload = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "digital.pdf",
                make_pdf(["Playable local audio."]),
                "application/pdf",
            )
        },
    ).json()
    client.post(f"/api/books/{upload['book_id']}/process-text")
    client.post(f"/api/books/{upload['book_id']}/prepare-audio")

    response = client.get(f"/api/books/{upload['book_id']}/audio/1/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")


def test_rejects_audio_before_text_is_ready(client: TestClient) -> None:
    upload = client.post(
        "/api/books/images",
        files=[("files", ("page.png", b"not real text yet", "image/png"))],
        data={"rotations": "[0]"},
    )
    if upload.status_code != 200:
        upload = client.post(
            "/api/books/pdf",
            files={
                "file": (
                    "scanned.pdf",
                    make_pdf([None]),
                    "application/pdf",
                )
            },
        )

    response = client.post(f"/api/books/{upload.json()['book_id']}/prepare-audio")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "book_text_not_ready"
