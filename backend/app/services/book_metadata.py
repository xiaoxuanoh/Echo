import json
from pathlib import Path

from app.core.errors import EchoError
from app.models.books import BookRecord


class LocalBookMetadataService:
    """Writes inspectable milestone-two book metadata beside local uploads."""

    metadata_filename = "book.json"

    def save(self, book_directory: Path, book: BookRecord) -> Path:
        destination = book_directory / self.metadata_filename
        temporary_destination = book_directory / f".{self.metadata_filename}.tmp"
        try:
            temporary_destination.write_text(
                json.dumps(book.model_dump(mode="json"), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            temporary_destination.replace(destination)
        except OSError as error:
            temporary_destination.unlink(missing_ok=True)
            raise EchoError(
                "metadata_save_failed",
                "Echo prepared the pages but could not save the book information.",
                status_code=500,
            ) from error
        return destination
