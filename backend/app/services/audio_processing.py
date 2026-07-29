import logging
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from uuid import UUID, uuid4

from app.core.errors import EchoError
from app.models.documents import AudioSegmentRecord, DocumentRecord
from app.services.document_metadata import LocalDocumentMetadataService
from app.services.text_segmentation import TextSegmentationService
from app.services.tts import MockTtsProvider, TtsProvider


logger = logging.getLogger(__name__)


class DocumentAudioProcessingService:
    """Creates ordered audio segments from prepared page text."""

    def __init__(
        self,
        *,
        storage_root: Path,
        max_segment_characters: int,
        target_segment_seconds: int = 360,
        soft_max_segment_seconds: int = 420,
        min_segment_seconds: int = 30,
        tts_provider: TtsProvider | None = None,
        tts_provider_factory: Callable[[str | None], TtsProvider] | None = None,
        metadata: LocalDocumentMetadataService | None = None,
        store_audio_file: Callable[
            [DocumentRecord, AudioSegmentRecord, Path],
            None,
        ]
        | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.segmenter = TextSegmentationService(
            max_segment_characters,
            target_seconds=target_segment_seconds,
            soft_max_seconds=soft_max_segment_seconds,
            min_seconds=min_segment_seconds,
        )
        self.tts_provider = tts_provider or MockTtsProvider()
        self.tts_provider_factory = tts_provider_factory
        self.metadata = metadata or LocalDocumentMetadataService()
        self.store_audio_file = store_audio_file

    def document_directory(self, document_id: UUID) -> Path:
        return self.storage_root / str(document_id)

    def load_document(self, document_id: UUID) -> DocumentRecord:
        return self.metadata.load(self.document_directory(document_id))

    def _tts_provider_for(self, document: DocumentRecord) -> TtsProvider:
        if self.tts_provider_factory:
            return self.tts_provider_factory(document.tts_voice)
        return self.tts_provider

    def prepare_audio_job(self, document_id: UUID) -> DocumentRecord:
        document = self.load_document(document_id)
        if document.status == "ready" and document.audio_segments:
            raise EchoError(
                "book_audio_ready",
                "This document already has listening audio prepared.",
                status_code=409,
            )
        if document.status == "generating_audio" and document.audio_segments:
            now = datetime.now(UTC)
            for segment in document.audio_segments:
                if segment.processing_status in {"generating", "failed"}:
                    segment.processing_status = "pending"
                    segment.error_message = None
                    segment.updated_at = now
            document.error_message = None
            document.updated_at = now
            self.metadata.save(self.document_directory(document.id), document)
            return document
        if document.status != "text_ready":
            raise EchoError(
                "book_text_not_ready",
                "Prepare the page text before creating listening audio.",
                status_code=409,
            )
        if any(page.processing_status != "completed" for page in document.pages):
            raise EchoError(
                "pages_not_ready",
                "All pages need text before Echo can create listening audio.",
                status_code=409,
            )
        self._tts_provider_for(document)

        drafts = self.segmenter.segment_pages(document.pages)
        if not drafts:
            raise EchoError(
                "no_text_to_read",
                "Echo could not find prepared text to turn into audio.",
                status_code=409,
            )

        now = datetime.now(UTC)
        document.audio_segments = [
            AudioSegmentRecord(
                id=uuid4(),
                document_id=document.id,
                page_id=draft.page_id,
                segment_number=index,
                source_text=draft.source_text,
                processing_status="pending",
                created_at=now,
                updated_at=now,
            )
            for index, draft in enumerate(drafts, start=1)
        ]
        document.status = "generating_audio"
        document.error_message = None
        document.updated_at = now
        self.metadata.save(self.document_directory(document.id), document)
        return document

    def process_audio(self, document_id: UUID) -> None:
        document = self.load_document(document_id)
        audio_directory = self.document_directory(document_id) / "audio"
        tts_provider = self._tts_provider_for(document)

        for segment in sorted(document.audio_segments, key=lambda item: item.segment_number):
            if segment.processing_status == "completed":
                continue
            segment.processing_status = "generating"
            segment.error_message = None
            segment.updated_at = datetime.now(UTC)
            document.status = "generating_audio"
            document.updated_at = segment.updated_at
            self.metadata.save(self.document_directory(document.id), document)

            try:
                filename = (
                    f"segment-{segment.segment_number:04d}."
                    f"{tts_provider.audio_file_extension}"
                )
                audio_path = audio_directory / filename
                duration = tts_provider.synthesize(segment.source_text, audio_path)
                segment.audio_storage_path = f"audio/{filename}"
                if self.store_audio_file is not None:
                    self.store_audio_file(document, segment, audio_path)
                segment.duration_seconds = duration
                segment.processing_status = "completed"
            except Exception:
                segment.processing_status = "failed"
                segment.error_message = "Echo could not create audio for this segment."
                logger.exception(
                    "Unexpected audio failure for document %s segment %s",
                    document.id,
                    segment.segment_number,
                )

            segment.updated_at = datetime.now(UTC)
            document.updated_at = segment.updated_at
            self.metadata.save(self.document_directory(document.id), document)

        self._finalize_document(document)

    def _finalize_document(self, document: DocumentRecord) -> None:
        failed_segments = [
            segment
            for segment in document.audio_segments
            if segment.processing_status == "failed"
        ]
        if failed_segments:
            document.status = "failed"
            document.error_message = (
                f"{len(failed_segments)} audio segment"
                f"{'s' if len(failed_segments) != 1 else ''} need another try."
            )
        elif document.audio_segments and all(
            segment.processing_status == "completed"
            for segment in document.audio_segments
        ):
            document.status = "ready"
            document.error_message = None
        document.updated_at = datetime.now(UTC)
        self.metadata.save(self.document_directory(document.id), document)
