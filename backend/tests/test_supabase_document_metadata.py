import json
import http.client
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.models.documents import AudioSegmentRecord, DocumentPageRecord, DocumentRecord
from app.services.document_metadata import SupabaseDocumentMetadataService


DOCUMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
PAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
SEGMENT_ID = UUID("55555555-5555-4555-8555-555555555555")
USER_ID = UUID("66666666-6666-4666-8666-666666666666")
NOW = datetime(2026, 7, 29, 8, 30, tzinfo=UTC)


class FakeResponse:
    def __init__(self, body: object | None = None) -> None:
        self.body = b"" if body is None else json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_supabase_metadata_save_writes_document_page_and_audio_rows(
    monkeypatch,
) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = SupabaseDocumentMetadataService(
        supabase_url="https://example.supabase.co",
        service_role_key="secret",
    )
    document = _document_record()

    service.save(Path(str(DOCUMENT_ID)), document)

    assert [request.get_method() for request in requests] == [
        "POST",
        "DELETE",
        "POST",
        "POST",
    ]
    document_payload = json.loads(requests[0].data.decode("utf-8"))[0]
    page_payload = json.loads(requests[2].data.decode("utf-8"))[0]
    segment_payload = json.loads(requests[3].data.decode("utf-8"))[0]
    assert document_payload["id"] == str(DOCUMENT_ID)
    assert document_payload["user_id"] == str(USER_ID)
    assert requests[1].full_url.endswith(
        f"/rest/v1/document_pages?document_id=eq.{DOCUMENT_ID}",
    )
    assert "on_conflict=id" in requests[2].full_url
    assert "on_conflict=id" in requests[3].full_url
    assert page_payload["crop_left"] == 0.1
    assert page_payload["crop_top"] == 0.2
    assert page_payload["crop_right"] == 0.9
    assert page_payload["crop_bottom"] == 0.8
    assert page_payload["warning_messages"] == [
        "This page contains chart or figure text. Please review the extracted "
        "text before generating audio."
    ]
    assert segment_payload["audio_storage_path"] == "audio/segment-0001.mp3"


def test_supabase_metadata_save_removes_stale_page_rows_when_none_remain(
    monkeypatch,
) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = SupabaseDocumentMetadataService(
        supabase_url="https://example.supabase.co",
        service_role_key="secret",
    )
    document = _document_record().model_copy(update={"pages": [], "audio_segments": []})

    service.save(Path(str(DOCUMENT_ID)), document)

    assert [request.get_method() for request in requests] == ["POST", "DELETE"]
    assert requests[1].full_url.endswith(
        f"/rest/v1/document_pages?document_id=eq.{DOCUMENT_ID}",
    )


def test_supabase_metadata_load_rebuilds_document_record(monkeypatch) -> None:
    responses = [
        [_document_row()],
        [_page_row()],
        [_audio_segment_row()],
    ]

    def fake_urlopen(request, timeout):
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = SupabaseDocumentMetadataService(
        supabase_url="https://example.supabase.co",
        service_role_key="secret",
    )

    document = service.load(Path(str(DOCUMENT_ID)))

    assert document.id == DOCUMENT_ID
    assert document.user_id == USER_ID
    assert document.pages[0].crop_left == 0.1
    assert document.pages[0].processed_image_path == "pages/page-0001.png"
    assert document.pages[0].warning_messages == [
        "This page contains chart or figure text. Please review the extracted "
        "text before generating audio."
    ]
    assert document.audio_segments[0].audio_storage_path == "audio/segment-0001.mp3"


def test_supabase_metadata_get_retries_incomplete_chunked_response(monkeypatch) -> None:
    responses = [
        http.client.IncompleteRead(b"", 191),
        [{"id": str(DOCUMENT_ID), "status": "ready"}],
    ]

    def fake_urlopen(request, timeout):
        del request, timeout
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = SupabaseDocumentMetadataService(
        supabase_url="https://example.supabase.co",
        service_role_key="secret",
    )

    result = service._request_json("GET", "documents")

    assert result == [{"id": str(DOCUMENT_ID), "status": "ready"}]
    assert responses == []


def test_supabase_metadata_post_retries_incomplete_chunked_response(monkeypatch) -> None:
    responses = [http.client.IncompleteRead(b"", 191), None]
    requests = []

    def fake_urlopen(request, timeout):
        del timeout
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    service = SupabaseDocumentMetadataService(
        supabase_url="https://example.supabase.co",
        service_role_key="secret",
    )

    result = service._request_json(
        "POST",
        "documents",
        query={"on_conflict": "id"},
        body=[{"id": str(DOCUMENT_ID)}],
        prefer="resolution=merge-duplicates,return=minimal",
        expect_json=False,
    )

    assert result is None
    assert [request.get_method() for request in requests] == ["POST", "POST"]
    assert responses == []


def _document_record() -> DocumentRecord:
    return DocumentRecord(
        id=DOCUMENT_ID,
        library_book_id=DOCUMENT_ID,
        user_id=USER_ID,
        title="Example",
        recording_title=None,
        target_language="cantonese",
        tts_voice="zh-HK-HiuMaanNeural",
        original_filename="example.pdf",
        source_type="pdf",
        source_storage_path="source.pdf",
        total_pages=1,
        status="ready",
        pages=[
            DocumentPageRecord(
                id=PAGE_ID,
                book_id=DOCUMENT_ID,
                page_number=1,
                original_filename=None,
                processed_image_path="pages/page-0001.png",
                extraction_method="ocr",
                extracted_text="Prepared text.",
                warning_messages=[
                    "This page contains chart or figure text. Please review the "
                    "extracted text before generating audio."
                ],
                crop_left=0.1,
                crop_top=0.2,
                crop_right=0.9,
                crop_bottom=0.8,
                processing_status="completed",
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        audio_segments=[
            AudioSegmentRecord(
                id=SEGMENT_ID,
                book_id=DOCUMENT_ID,
                page_id=PAGE_ID,
                segment_number=1,
                source_text="Prepared text.",
                audio_storage_path="audio/segment-0001.mp3",
                duration_seconds=3.5,
                processing_status="completed",
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        created_at=NOW,
        updated_at=NOW,
    )


def _document_row() -> dict[str, object]:
    return {
        "id": str(DOCUMENT_ID),
        "user_id": str(USER_ID),
        "library_document_id": str(DOCUMENT_ID),
        "title": "Example",
        "recording_title": None,
        "target_language": "cantonese",
        "tts_voice": "zh-HK-HiuMaanNeural",
        "original_filename": "example.pdf",
        "source_type": "pdf",
        "source_storage_path": "source.pdf",
        "total_pages": 1,
        "status": "ready",
        "error_message": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }


def _page_row() -> dict[str, object]:
    return {
        "id": str(PAGE_ID),
        "document_id": str(DOCUMENT_ID),
        "user_id": str(USER_ID),
        "page_number": 1,
        "original_filename": None,
        "original_image_storage_path": None,
        "processed_image_storage_path": "pages/page-0001.png",
        "extraction_method": "ocr",
        "extracted_text": "Prepared text.",
        "error_message": None,
        "warning_messages": [
            "This page contains chart or figure text. Please review the extracted "
            "text before generating audio."
        ],
        "crop_left": 0.1,
        "crop_top": 0.2,
        "crop_right": 0.9,
        "crop_bottom": 0.8,
        "rotation_degrees": 0,
        "processing_status": "completed",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }


def _audio_segment_row() -> dict[str, object]:
    return {
        "id": str(SEGMENT_ID),
        "document_id": str(DOCUMENT_ID),
        "user_id": str(USER_ID),
        "page_id": str(PAGE_ID),
        "segment_number": 1,
        "source_text": "Prepared text.",
        "audio_storage_path": "audio/segment-0001.mp3",
        "duration_seconds": 3.5,
        "processing_status": "completed",
        "error_message": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
