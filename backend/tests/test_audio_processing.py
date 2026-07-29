from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
import subprocess
import shutil
from uuid import UUID
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.api.routes.books import _resolve_ffmpeg_path
from app.main import create_app
from app.models.documents import DocumentPageRecord
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.tts import (
    AzureSpeechTtsProvider,
    EdgeTtsProvider,
    MockTtsProvider,
    create_tts_provider,
)
from app.services.text_segmentation import TextSegmentationService
from tests.conftest import make_pdf


def test_segments_text_without_exceeding_limit() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    page_id = uuid4()
    page = DocumentPageRecord(
        id=page_id,
        document_id=document_id,
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


def test_segments_merge_visual_pdf_line_breaks_before_audio() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    page_id = uuid4()
    page = DocumentPageRecord(
        id=page_id,
        document_id=document_id,
        page_number=1,
        extraction_method="embedded_text",
        extracted_text=(
            "「進可攻、退可守」的期權實戰配置\n"
            "想像一下，你是一個在香港生活的上班族，儘管在參與股票買賣方面擁有 \n"
            "長期經驗或偶然只會跟着市場趨勢買賣股票，但因為大部分時間都是高買\n"
            "\n"
            "低賣，所以感覺很沮喪。\n"
            "證券價格走勢而上落。）你心裏想：「如果我也能從這些機會中分一杯\n"
            "\n"
            "羹，那有多好！」"
        ),
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )
    service = TextSegmentationService(max_characters=300)

    segments = service.segment_pages([page])

    assert [segment.source_text for segment in segments] == [
        (
            "「進可攻、退可守」的期權實戰配置\n\n"
            "想像一下，你是一個在香港生活的上班族，儘管在參與股票買賣方面擁有"
            "長期經驗或偶然只會跟着市場趨勢買賣股票，但因為大部分時間都是高買\n\n"
            "低賣，所以感覺很沮喪。 證券價格走勢而上落。）你心裏想：「如果我也能從這些機會中分一杯羹，那有多好！」"
        )
    ]


def test_segments_attach_short_heading_to_next_audio_part() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    page_id = uuid4()
    title = "「進可攻、退可守」的期權實戰配置"
    body = (
        "想像一下，你是一個在香港生活的上班族，儘管在參與股票買賣方面擁有"
        "長期經驗或偶然只會跟着市場趨勢買賣股票，但因為大部分時間都是高買"
        "低賣，所以感覺很沮喪。"
        + "股票期權能讓投資者在波動市場中更靈活地管理風險和收入。"
        * 35
    )
    page = DocumentPageRecord(
        id=page_id,
        document_id=document_id,
        page_number=1,
        extraction_method="embedded_text",
        extracted_text=f"{title}\n{body}",
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )
    service = TextSegmentationService(max_characters=3000)

    segments = service.segment_pages([page])

    assert len(segments) == 1
    assert segments[0].source_text.startswith(f"{title}\n\n想像一下")
    assert title not in [segment.source_text for segment in segments]
    assert all(len(segment.source_text) <= 3000 for segment in segments)


def test_segments_do_not_create_tiny_tail_for_slightly_long_cjk_page() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    page_id = uuid4()
    title = "「進可攻、退可守」的期權實戰配置"
    body = (
        "想像一下，你是一個在香港生活的上班族，儘管在參與股票買賣方面擁有"
        "長期經驗或偶然只會跟着市場趨勢買賣股票，但因為大部分時間都是高買"
        "低賣，所以感覺很沮喪。"
        + "股票期權能讓投資者在波動市場中更靈活地管理風險和收入。"
        * 32
        + "市場參與者類型繁多，有些是純粹的投機者，有些是長期投資者，也"
    )
    page = DocumentPageRecord(
        id=page_id,
        document_id=document_id,
        page_number=1,
        extraction_method="embedded_text",
        extracted_text=f"{title}\n{body}",
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )
    service = TextSegmentationService(max_characters=3000)

    segments = service.segment_pages([page])

    assert len(segments) == 1
    assert segments[0].source_text.endswith(
        "市場參與者類型繁多，有些是純粹的投機者，有些是長期投資者，也"
    )


def test_segments_normalize_cjk_radicals_before_audio() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()
    page_id = uuid4()
    page = DocumentPageRecord(
        id=page_id,
        document_id=document_id,
        page_number=1,
        extraction_method="embedded_text",
        extracted_text="⽅⾯擁有 ⻑期經驗",
        processing_status="completed",
        created_at=now,
        updated_at=now,
    )
    service = TextSegmentationService(max_characters=300)

    segments = service.segment_pages([page])

    assert [segment.source_text for segment in segments] == ["方面擁有長期經驗"]


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
    assert audio.json()["target_language"] is None
    assert audio.json()["tts_voice"] is None
    assert audio.json()["segments"][0]["processing_status"] == "completed"
    assert audio.json()["segments"][0]["audio_url"].endswith("/audio/1/file")

    saved = LocalDocumentMetadataService().load(storage_path / upload["book_id"])
    assert saved.status == "ready"
    assert saved.audio_segments[0].audio_storage_path == "audio/segment-0001.wav"
    assert (storage_path / upload["book_id"] / "audio" / "segment-0001.wav").exists()


def test_tts_factory_keeps_mock_mode_as_default(storage_path: Path) -> None:
    settings = Settings(_env_file=None, local_storage_path=storage_path)

    provider = create_tts_provider(settings)

    assert isinstance(provider, MockTtsProvider)


def test_tts_factory_selects_azure_when_mock_mode_is_disabled(
    storage_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        use_mock_tts=False,
        azure_speech_key="test-key",
        azure_speech_region="eastus",
        azure_speech_voice="zh-HK-HiuMaanNeural",
    )

    provider = create_tts_provider(settings)

    assert isinstance(provider, AzureSpeechTtsProvider)


def test_tts_factory_selects_edge_when_configured(
    storage_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        use_mock_tts=False,
        tts_provider="edge",
        edge_tts_voice="zh-CN-XiaoxiaoNeural",
    )

    provider = create_tts_provider(settings)

    assert isinstance(provider, EdgeTtsProvider)
    assert provider.audio_file_extension == "mp3"


def test_tts_factory_uses_voice_override(storage_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        use_mock_tts=False,
        tts_provider="edge",
        edge_tts_voice="zh-CN-XiaoxiaoNeural",
    )

    provider = create_tts_provider(settings, voice_override="zh-HK-HiuMaanNeural")

    assert isinstance(provider, EdgeTtsProvider)
    assert provider.voice == "zh-HK-HiuMaanNeural"


def test_azure_mode_reports_missing_configuration(storage_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        use_mock_tts=False,
    )
    with TestClient(create_app(settings)) as real_tts_client:
        upload = real_tts_client.post(
            "/api/books/pdf",
            files={
                "file": (
                    "digital.pdf",
                    make_pdf(["Text ready, but Azure is not configured."]),
                    "application/pdf",
                )
            },
        ).json()
        real_tts_client.post(f"/api/books/{upload['book_id']}/process-text")

        response = real_tts_client.post(f"/api/books/{upload['book_id']}/prepare-audio")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "tts_configuration_missing"
    assert response.json()["error"]["details"]["missing"] == [
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
    ]


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


def test_supabase_storage_audio_uploads_serves_downloads_and_deletes(
    storage_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = UUID("88888888-8888-4888-8888-888888888888")
    fake_storage = FakeSupabaseStorage()
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="secret",
        supabase_storage_bucket_books="documents-source",
        supabase_storage_bucket_pages="documents-pages",
        supabase_storage_bucket_audio="documents-audio",
        max_pdf_size_mb=1,
    )
    monkeypatch.setattr(
        "app.api.routes.books._verify_supabase_user_id",
        lambda _, token: user_id,
    )
    monkeypatch.setattr(
        "app.api.routes.books._metadata_service",
        lambda _: LocalDocumentMetadataService(),
    )
    monkeypatch.setattr(
        "app.api.routes.books._file_storage_service",
        lambda _: fake_storage,
    )

    with TestClient(create_app(settings)) as authed_client:
        upload = authed_client.post(
            "/api/books/pdf",
            headers={"Authorization": "Bearer token"},
            files={
                "file": (
                    "digital.pdf",
                    make_pdf(["Playable stored audio."]),
                    "application/pdf",
                )
            },
        ).json()
        authed_client.post(
            f"/api/books/{upload['book_id']}/process-text",
            headers={"Authorization": "Bearer token"},
        )
        authed_client.post(
            f"/api/books/{upload['book_id']}/prepare-audio",
            headers={"Authorization": "Bearer token"},
        )
        local_audio = (
            storage_path
            / upload["book_id"]
            / "audio"
            / "segment-0001.wav"
        )
        original_audio = local_audio.read_bytes()
        local_audio.unlink()

        playback = authed_client.get(
            f"/api/books/{upload['book_id']}/audio/1/file",
            headers={"Authorization": "Bearer token"},
        )
        local_audio.unlink()
        download = authed_client.get(
            f"/api/books/{upload['book_id']}/audio/download",
            headers={"Authorization": "Bearer token"},
        )
        delete = authed_client.delete(
            f"/api/books/{upload['book_id']}",
            headers={"Authorization": "Bearer token"},
        )

    audio_key = ("documents-audio", f"{user_id}/{upload['book_id']}/audio/segment-0001.wav")
    assert fake_storage.objects[audio_key] == original_audio
    assert playback.status_code == 200
    assert playback.content == original_audio
    assert download.status_code == 200
    with ZipFile(BytesIO(download.content)) as archive:
        assert archive.read("part-001.wav") == original_audio
    assert delete.status_code == 200
    assert ("documents-audio", f"{user_id}/{upload['book_id']}") in fake_storage.deleted_prefixes


def test_downloads_ready_recording_audio_as_zip(client: TestClient) -> None:
    upload = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "chapter-one.pdf",
                make_pdf(["First playable page.", "Second playable page."]),
                "application/pdf",
            )
        },
    ).json()
    client.post(f"/api/books/{upload['book_id']}/process-text")
    client.post(f"/api/books/{upload['book_id']}/prepare-audio")

    response = client.get(f"/api/books/{upload['book_id']}/audio/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="chapter-one.zip"'
    )
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == ["part-001.wav", "part-002.wav"]
        assert archive.read("part-001.wav").startswith(b"RIFF")
        assert archive.read("part-002.wav").startswith(b"RIFF")


def test_downloads_ready_folder_audio_as_one_mp3_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg_commands: list[list[str]] = []
    ffmpeg_input_lists: list[str] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        ffmpeg_commands.append(command)
        ffmpeg_input_lists.append(Path(command[10]).read_text(encoding="utf-8"))
        Path(command[-1]).write_bytes(b"ID3 combined audio")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.api.routes.books.subprocess.run", fake_run)
    first = client.post(
        "/api/books/pdf",
        files={
            "file": (
                "chapter-one.pdf",
                make_pdf(["First playable page."]),
                "application/pdf",
            )
        },
    ).json()
    second = client.post(
        "/api/books/pdf",
        data={"library_book_id": first["book_id"]},
        files={
            "file": (
                "chapter-two.pdf",
                make_pdf(["Second playable page."]),
                "application/pdf",
            )
        },
    ).json()
    client.post(f"/api/books/{first['book_id']}/process-text")
    client.post(f"/api/books/{first['book_id']}/prepare-audio")
    client.post(f"/api/books/{second['book_id']}/process-text")
    client.post(f"/api/books/{second['book_id']}/prepare-audio")

    response = client.get(f"/api/books/folders/{first['book_id']}/audio/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="chapter-one.mp3"'
    )
    assert response.content == b"ID3 combined audio"
    assert len(ffmpeg_commands) == 1
    assert ffmpeg_input_lists[0].index(first["book_id"]) < ffmpeg_input_lists[0].index(
        second["book_id"],
    )
    assert Path(ffmpeg_commands[0][0]).name == "ffmpeg"
    assert ffmpeg_commands[0][1:10] == [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
    ]
    assert ffmpeg_commands[0][-6:-1] == [
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
    ]


def test_supabase_storage_combined_audio_download_fetches_segments(
    storage_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = UUID("99999999-9999-4999-8999-999999999999")
    fake_storage = FakeSupabaseStorage()
    settings = Settings(
        _env_file=None,
        local_storage_path=storage_path,
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="secret",
        supabase_storage_bucket_books="documents-source",
        supabase_storage_bucket_pages="documents-pages",
        supabase_storage_bucket_audio="documents-audio",
        max_pdf_size_mb=1,
    )
    ffmpeg_input_lists: list[str] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, text
        ffmpeg_input_lists.append(Path(command[10]).read_text(encoding="utf-8"))
        Path(command[-1]).write_bytes(b"ID3 stored combined audio")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.api.routes.books.subprocess.run", fake_run)
    monkeypatch.setattr(
        "app.api.routes.books._verify_supabase_user_id",
        lambda _, token: user_id,
    )
    monkeypatch.setattr(
        "app.api.routes.books._metadata_service",
        lambda _: LocalDocumentMetadataService(),
    )
    monkeypatch.setattr(
        "app.api.routes.books._file_storage_service",
        lambda _: fake_storage,
    )

    with TestClient(create_app(settings)) as authed_client:
        first = authed_client.post(
            "/api/books/pdf",
            headers={"Authorization": "Bearer token"},
            files={
                "file": (
                    "chapter-one.pdf",
                    make_pdf(["First stored audio."]),
                    "application/pdf",
                )
            },
        ).json()
        second = authed_client.post(
            "/api/books/pdf",
            headers={"Authorization": "Bearer token"},
            data={"library_book_id": first["book_id"]},
            files={
                "file": (
                    "chapter-two.pdf",
                    make_pdf(["Second stored audio."]),
                    "application/pdf",
                )
            },
        ).json()
        for upload in (first, second):
            authed_client.post(
                f"/api/books/{upload['book_id']}/process-text",
                headers={"Authorization": "Bearer token"},
            )
            authed_client.post(
                f"/api/books/{upload['book_id']}/prepare-audio",
                headers={"Authorization": "Bearer token"},
            )
            shutil.rmtree(storage_path / upload["book_id"] / "audio")

        response = authed_client.get(
            f"/api/books/folders/{first['book_id']}/audio/download",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.content == b"ID3 stored combined audio"
    assert first["book_id"] in ffmpeg_input_lists[0]
    assert second["book_id"] in ffmpeg_input_lists[0]


def test_resolves_homebrew_ffmpeg_when_server_path_is_sparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.routes.books.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "app.api.routes.books.Path.exists",
        lambda path: str(path) == "/opt/homebrew/bin/ffmpeg",
    )

    assert _resolve_ffmpeg_path("ffmpeg") == "/opt/homebrew/bin/ffmpeg"


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


class FakeSupabaseStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.deleted_prefixes: list[tuple[str, str]] = []

    def upload_file(
        self,
        *,
        bucket: str,
        object_path: str,
        source: Path,
        content_type: str,
    ) -> None:
        del content_type
        self.objects[(bucket, object_path)] = source.read_bytes()

    def read_file(self, *, bucket: str, object_path: str) -> bytes:
        return self.objects[(bucket, object_path)]

    def download_file(
        self,
        *,
        bucket: str,
        object_path: str,
        destination: Path,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[(bucket, object_path)])
        return destination

    def delete_prefix(self, *, bucket: str, prefix: str) -> None:
        self.deleted_prefixes.append((bucket, prefix))
