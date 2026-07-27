import json
from pathlib import Path

from app.core.errors import EchoError
from app.models.documents import DocumentRecord


class LocalDocumentMetadataService:
    """Writes inspectable local document metadata beside local uploads."""

    metadata_filename = "book.json"

    def list_documents(self, storage_root: Path) -> list[DocumentRecord]:
        documents: list[DocumentRecord] = []
        if not storage_root.exists():
            return documents

        for child in storage_root.iterdir():
            if not child.is_dir():
                continue
            metadata_path = child / self.metadata_filename
            if not metadata_path.exists():
                continue
            documents.append(self.load(child))

        return sorted(documents, key=lambda document: document.updated_at, reverse=True)

    def load(self, document_directory: Path) -> DocumentRecord:
        source = document_directory / self.metadata_filename
        try:
            return DocumentRecord.model_validate_json(source.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise EchoError(
                "book_not_found",
                "Echo could not find that temporary document.",
                status_code=404,
            ) from error
        except (OSError, ValueError) as error:
            raise EchoError(
                "document_metadata_invalid",
                "Echo could not read the temporary upload information.",
                status_code=500,
            ) from error

    def save(self, document_directory: Path, document: DocumentRecord) -> Path:
        destination = document_directory / self.metadata_filename
        temporary_destination = document_directory / f".{self.metadata_filename}.tmp"
        try:
            temporary_destination.write_text(
                json.dumps(
                    document.model_dump(mode="json", by_alias=True),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary_destination.replace(destination)
        except OSError as error:
            temporary_destination.unlink(missing_ok=True)
            raise EchoError(
                "metadata_save_failed",
                "Echo prepared the pages but could not save the document information.",
                status_code=500,
            ) from error
        return destination
