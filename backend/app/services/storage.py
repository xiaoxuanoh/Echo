from pathlib import Path
import json
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID

from fastapi import UploadFile

from app.core.errors import EchoError


class LocalStorageService:
    """Stores prototype uploads in UUID-scoped local directories."""

    chunk_size = 1024 * 1024

    def __init__(self, root: Path) -> None:
        self.root = root

    def create_document_directory(self, document_id: UUID) -> Path:
        directory = self.root / str(document_id)
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


class SupabaseStorageService:
    """Stores private binary document assets in Supabase Storage."""

    def __init__(self, *, supabase_url: str, service_role_key: str) -> None:
        self.storage_url = f"{supabase_url.rstrip('/')}/storage/v1"
        self.service_role_key = service_role_key

    def upload_file(
        self,
        *,
        bucket: str,
        object_path: str,
        source: Path,
        content_type: str,
    ) -> None:
        try:
            body = source.read_bytes()
        except OSError as error:
            raise EchoError(
                "storage_source_missing",
                "Echo could not find a prepared file to store.",
                status_code=500,
            ) from error

        self._request(
            "POST",
            f"object/{bucket}/{object_path}",
            body=body,
            headers={
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            expect_body=False,
        )

    def download_file(
        self,
        *,
        bucket: str,
        object_path: str,
        destination: Path,
    ) -> Path:
        body = self.read_file(bucket=bucket, object_path=object_path)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        except OSError as error:
            raise EchoError(
                "storage_download_save_failed",
                "Echo could not prepare the stored file locally.",
                status_code=500,
            ) from error
        return destination

    def read_file(self, *, bucket: str, object_path: str) -> bytes:
        return self._request("GET", f"object/{bucket}/{object_path}")

    def delete_prefix(self, *, bucket: str, prefix: str) -> None:
        self._request(
            "DELETE",
            f"object/{bucket}",
            body=json.dumps({"prefixes": [prefix]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            expect_body=False,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expect_body: bool = True,
    ) -> bytes:
        safe_path = "/".join(
            urllib.parse.quote(part, safe="")
            for part in path.split("/")
            if part
        )
        request = urllib.request.Request(
            f"{self.storage_url}/{safe_path}",
            data=body,
            method=method,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read()
        except urllib.error.HTTPError as error:
            raise EchoError(
                "supabase_storage_failed",
                "Echo could not save or load your document files.",
                status_code=502,
                details={"status_code": error.code},
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise EchoError(
                "supabase_storage_unavailable",
                "Echo could not reach document file storage right now.",
                status_code=503,
            ) from error

        return response_body if expect_body else b""
