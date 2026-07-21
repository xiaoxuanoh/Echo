from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import EchoError


class LocalStorageService:
    """Stores milestone-one uploads in UUID-scoped local directories."""

    chunk_size = 1024 * 1024

    def __init__(self, root: Path) -> None:
        self.root = root

    def create_book_directory(self, book_id: UUID) -> Path:
        directory = self.root / str(book_id)
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    async def save_upload(
        self,
        upload: UploadFile,
        destination: Path,
        max_bytes: int,
    ) -> int:
        size = 0
        try:
            with destination.open("xb") as output:
                while chunk := await upload.read(self.chunk_size):
                    size += len(chunk)
                    if size > max_bytes:
                        raise EchoError(
                            "file_too_large",
                            "This file is larger than the allowed upload size.",
                            status_code=413,
                            details={"max_bytes": max_bytes},
                        )
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        if size == 0:
            destination.unlink(missing_ok=True)
            raise EchoError("empty_file", "The selected file is empty.")
        return size
