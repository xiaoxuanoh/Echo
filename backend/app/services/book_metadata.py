import json
from pathlib import Path

from app.core.errors import EchoError
from app.models.books import BookRecord


class LocalBookMetadataService:
    """Writes inspectable milestone-two book metadata beside local uploads."""

    metadata_filename = "book.json"

    def list_books(self, storage_root: Path) -> list[BookRecord]:
        books: list[BookRecord] = []
        if not storage_root.exists():
            return books

        for child in storage_root.iterdir():
            if not child.is_dir():
                continue
            metadata_path = child / self.metadata_filename
            if not metadata_path.exists():
                continue
            books.append(self.load(child))

        return sorted(books, key=lambda book: book.updated_at, reverse=True)

    def load(self, book_directory: Path) -> BookRecord:
        source = book_directory / self.metadata_filename
        try:
            return BookRecord.model_validate_json(source.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise EchoError(
                "book_not_found",
                "Echo could not find that temporary book.",
                status_code=404,
            ) from error
        except (OSError, ValueError) as error:
            raise EchoError(
                "book_metadata_invalid",
                "Echo could not read the temporary book information.",
                status_code=500,
            ) from error

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
