from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.book_metadata import LocalBookMetadataService
from tests.conftest import make_pdf


def test_lists_empty_local_book_library(client: TestClient) -> None:
    response = client.get("/api/books")

    assert response.status_code == 200
    assert response.json() == {"folders": []}


def test_lists_local_books_by_latest_update(
    client: TestClient,
    storage_path: Path,
) -> None:
    older_upload = client.post(
        "/api/books/pdf",
        files={"file": ("older.pdf", make_pdf(["Older text."]), "application/pdf")},
    ).json()
    newer_upload = client.post(
        "/api/books/pdf",
        files={"file": ("newer.pdf", make_pdf(["Newer text."]), "application/pdf")},
    ).json()

    metadata = LocalBookMetadataService()
    older = metadata.load(storage_path / older_upload["book_id"])
    newer = metadata.load(storage_path / newer_upload["book_id"])
    older.updated_at = datetime(2026, 7, 22, tzinfo=UTC)
    newer.updated_at = datetime(2026, 7, 24, tzinfo=UTC)
    metadata.save(storage_path / older_upload["book_id"], older)
    metadata.save(storage_path / newer_upload["book_id"], newer)

    response = client.get("/api/books")

    assert response.status_code == 200
    result = response.json()
    assert [folder["id"] for folder in result["folders"]] == [
        newer_upload["book_id"],
        older_upload["book_id"],
    ]
    assert result["folders"][0]["title"] == "newer"
    assert result["folders"][0]["recording_count"] == 1
    assert result["folders"][0]["total_pages"] == 1
    assert result["folders"][0]["processing_status"] == "uploaded"
    assert result["folders"][0]["processing_active"] is False
    assert result["folders"][0]["latest_recording_at"] == "2026-07-24T00:00:00Z"
    assert result["folders"][0]["recordings"][0] == {
        "id": newer_upload["book_id"],
        "library_book_id": newer_upload["book_id"],
        "title": "newer",
        "recording_title": None,
        "original_filename": "newer.pdf",
        "source_type": "pdf",
        "total_pages": 1,
        "processing_status": "uploaded",
        "error_message": None,
        "completed_pages": 0,
        "failed_pages": 0,
        "audio_segment_count": 0,
        "processing_active": False,
        "created_at": newer.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": "2026-07-24T00:00:00Z",
    }


def test_groups_existing_same_title_uploads_as_recordings(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["First text."]), "application/pdf")},
    ).json()
    second = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["Second text."]), "application/pdf")},
    ).json()

    response = client.get("/api/books")

    assert response.status_code == 200
    folders = response.json()["folders"]
    assert len(folders) == 1
    assert folders[0]["id"] == first["book_id"]
    assert folders[0]["title"] == "same"
    assert folders[0]["recording_count"] == 2
    assert {recording["id"] for recording in folders[0]["recordings"]} == {
        first["book_id"],
        second["book_id"],
    }


def test_uploads_pdf_recording_to_existing_library_book(
    client: TestClient,
    storage_path: Path,
) -> None:
    first = client.post(
        "/api/books/pdf",
        files={"file": ("book.pdf", make_pdf(["First text."]), "application/pdf")},
    ).json()

    second = client.post(
        "/api/books/pdf",
        data={"library_book_id": first["book_id"]},
        files={
            "file": ("chapter-two.pdf", make_pdf(["Second text."]), "application/pdf")
        },
    )

    assert second.status_code == 200
    saved = LocalBookMetadataService().load(storage_path / second.json()["book_id"])
    assert str(saved.library_book_id) == first["book_id"]
    assert saved.title == "book"
    assert saved.recording_title == "chapter-two"
    folder = client.get("/api/books").json()["folders"][0]
    assert folder["id"] == first["book_id"]
    assert folder["title"] == "book"
    assert folder["recording_count"] == 2


def test_upload_to_unknown_library_book_returns_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/books/pdf",
        data={"library_book_id": "11111111-1111-4111-8111-111111111111"},
        files={"file": ("book.pdf", make_pdf(["Text."]), "application/pdf")},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "library_book_not_found"


def test_renames_a_local_book_folder(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/pdf",
        files={"file": ("original.pdf", make_pdf(["Text."]), "application/pdf")},
    ).json()

    response = client.patch(
        f"/api/books/folders/{upload['book_id']}",
        json={"title": "Renamed book"},
    )

    assert response.status_code == 200
    saved = LocalBookMetadataService().load(storage_path / upload["book_id"])
    assert saved.title == "Renamed book"
    assert str(saved.library_book_id) == upload["book_id"]
    assert client.get("/api/books").json()["folders"][0]["title"] == "Renamed book"


def test_deletes_one_recording_without_removing_folder(
    client: TestClient,
    storage_path: Path,
) -> None:
    first = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["First text."]), "application/pdf")},
    ).json()
    second = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["Second text."]), "application/pdf")},
    ).json()

    response = client.delete(f"/api/books/{second['book_id']}")

    assert response.status_code == 200
    assert (storage_path / first["book_id"]).exists()
    assert not (storage_path / second["book_id"]).exists()
    folder = client.get("/api/books").json()["folders"][0]
    assert folder["recording_count"] == 1
    assert folder["recordings"][0]["id"] == first["book_id"]


def test_renames_one_recording(
    client: TestClient,
    storage_path: Path,
) -> None:
    upload = client.post(
        "/api/books/pdf",
        files={"file": ("chapter.pdf", make_pdf(["Text."]), "application/pdf")},
    ).json()

    response = client.patch(
        f"/api/books/{upload['book_id']}",
        json={"title": "Chapter one"},
    )

    assert response.status_code == 200
    saved = LocalBookMetadataService().load(storage_path / upload["book_id"])
    assert saved.title == "chapter"
    assert saved.recording_title == "Chapter one"
    recording = client.get("/api/books").json()["folders"][0]["recordings"][0]
    assert recording["title"] == "chapter"
    assert recording["recording_title"] == "Chapter one"


def test_deletes_a_local_book_folder(
    client: TestClient,
    storage_path: Path,
) -> None:
    first = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["First text."]), "application/pdf")},
    ).json()
    second = client.post(
        "/api/books/pdf",
        files={"file": ("same.pdf", make_pdf(["Second text."]), "application/pdf")},
    ).json()

    response = client.delete(f"/api/books/folders/{first['book_id']}")

    assert response.status_code == 200
    assert not (storage_path / first["book_id"]).exists()
    assert not (storage_path / second["book_id"]).exists()
    assert client.get("/api/books").json() == {"folders": []}
