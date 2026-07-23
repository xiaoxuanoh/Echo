import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.core.errors import EchoError
from app.models.books import AudioSegmentRecord, BookRecord
from app.services.book_metadata import LocalBookMetadataService
from app.services.text_segmentation import TextSegmentationService
from app.services.tts import MockTtsProvider, TtsProvider


logger = logging.getLogger(__name__)


class BookAudioProcessingService:
    """Creates ordered audio segments from prepared page text."""

    def __init__(
        self,
        *,
        storage_root: Path,
        max_segment_characters: int,
        tts_provider: TtsProvider | None = None,
        metadata: LocalBookMetadataService | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.segmenter = TextSegmentationService(max_segment_characters)
        self.tts_provider = tts_provider or MockTtsProvider()
        self.metadata = metadata or LocalBookMetadataService()

    def book_directory(self, book_id: UUID) -> Path:
        return self.storage_root / str(book_id)

    def load_book(self, book_id: UUID) -> BookRecord:
        return self.metadata.load(self.book_directory(book_id))

    def prepare_audio_job(self, book_id: UUID) -> BookRecord:
        book = self.load_book(book_id)
        if book.status == "ready" and book.audio_segments:
            raise EchoError(
                "book_audio_ready",
                "This book already has listening audio prepared.",
                status_code=409,
            )
        if book.status == "generating_audio" and book.audio_segments:
            now = datetime.now(UTC)
            for segment in book.audio_segments:
                if segment.processing_status in {"generating", "failed"}:
                    segment.processing_status = "pending"
                    segment.error_message = None
                    segment.updated_at = now
            book.error_message = None
            book.updated_at = now
            self.metadata.save(self.book_directory(book.id), book)
            return book
        if book.status != "text_ready":
            raise EchoError(
                "book_text_not_ready",
                "Prepare the page text before creating listening audio.",
                status_code=409,
            )
        if any(page.processing_status != "completed" for page in book.pages):
            raise EchoError(
                "pages_not_ready",
                "All pages need text before Echo can create listening audio.",
                status_code=409,
            )

        drafts = self.segmenter.segment_pages(book.pages)
        if not drafts:
            raise EchoError(
                "no_text_to_read",
                "Echo could not find prepared text to turn into audio.",
                status_code=409,
            )

        now = datetime.now(UTC)
        book.audio_segments = [
            AudioSegmentRecord(
                id=uuid4(),
                book_id=book.id,
                page_id=draft.page_id,
                segment_number=index,
                source_text=draft.source_text,
                processing_status="pending",
                created_at=now,
                updated_at=now,
            )
            for index, draft in enumerate(drafts, start=1)
        ]
        book.status = "generating_audio"
        book.error_message = None
        book.updated_at = now
        self.metadata.save(self.book_directory(book.id), book)
        return book

    def process_audio(self, book_id: UUID) -> None:
        book = self.load_book(book_id)
        audio_directory = self.book_directory(book_id) / "audio"

        for segment in sorted(book.audio_segments, key=lambda item: item.segment_number):
            if segment.processing_status == "completed":
                continue
            segment.processing_status = "generating"
            segment.error_message = None
            segment.updated_at = datetime.now(UTC)
            book.status = "generating_audio"
            book.updated_at = segment.updated_at
            self.metadata.save(self.book_directory(book.id), book)

            try:
                filename = f"segment-{segment.segment_number:04d}.wav"
                duration = self.tts_provider.synthesize(
                    segment.source_text,
                    audio_directory / filename,
                )
                segment.audio_storage_path = f"audio/{filename}"
                segment.duration_seconds = duration
                segment.processing_status = "completed"
            except Exception:
                segment.processing_status = "failed"
                segment.error_message = "Echo could not create audio for this segment."
                logger.exception(
                    "Unexpected audio failure for book %s segment %s",
                    book.id,
                    segment.segment_number,
                )

            segment.updated_at = datetime.now(UTC)
            book.updated_at = segment.updated_at
            self.metadata.save(self.book_directory(book.id), book)

        self._finalize_book(book)

    def _finalize_book(self, book: BookRecord) -> None:
        failed_segments = [
            segment
            for segment in book.audio_segments
            if segment.processing_status == "failed"
        ]
        if failed_segments:
            book.status = "failed"
            book.error_message = (
                f"{len(failed_segments)} audio segment"
                f"{'s' if len(failed_segments) != 1 else ''} need another try."
            )
        elif book.audio_segments and all(
            segment.processing_status == "completed"
            for segment in book.audio_segments
        ):
            book.status = "ready"
            book.error_message = None
        book.updated_at = datetime.now(UTC)
        self.metadata.save(self.book_directory(book.id), book)
