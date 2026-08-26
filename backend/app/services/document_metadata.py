import json
import http.client
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.errors import EchoError
from app.models.documents import AudioSegmentRecord, DocumentPageRecord, DocumentRecord


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

    def delete(self, document_directory: Path) -> None:
        metadata_path = document_directory / self.metadata_filename
        metadata_path.unlink(missing_ok=True)


class SupabaseDocumentMetadataService:
    """Persists document metadata in Supabase while preserving DocumentRecord."""

    transient_status_codes = {503, 520}
    transient_retry_methods = {"GET", "HEAD", "POST"}

    def __init__(self, *, supabase_url: str, service_role_key: str) -> None:
        self.rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self.service_role_key = service_role_key

    def list_documents(self, storage_root: Path) -> list[DocumentRecord]:
        del storage_root
        documents = self._request_json(
            "GET",
            "documents",
            query={"select": "*", "order": "updated_at.desc"},
        )
        if not isinstance(documents, list):
            raise self._invalid_response_error()
        document_ids = [
            str(row["id"])
            for row in documents
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        ]
        pages = self._list_related_rows("document_pages", document_ids, "page_number.asc")
        segments = self._list_related_rows(
            "audio_segments",
            document_ids,
            "segment_number.asc",
        )
        return self._records_from_rows(documents, pages, segments)

    def load(self, document_directory: Path) -> DocumentRecord:
        document_id = document_directory.name
        documents = self._request_json(
            "GET",
            "documents",
            query={"select": "*", "id": f"eq.{document_id}", "limit": "1"},
        )
        if not isinstance(documents, list):
            raise self._invalid_response_error()
        if not documents:
            raise EchoError(
                "book_not_found",
                "Echo could not find that upload in your library.",
                status_code=404,
            )
        pages = self._request_json(
            "GET",
            "document_pages",
            query={
                "select": "*",
                "document_id": f"eq.{document_id}",
                "order": "page_number.asc",
            },
        )
        segments = self._request_json(
            "GET",
            "audio_segments",
            query={
                "select": "*",
                "document_id": f"eq.{document_id}",
                "order": "segment_number.asc",
            },
        )
        if not isinstance(pages, list) or not isinstance(segments, list):
            raise self._invalid_response_error()
        return self._record_from_rows(documents[0], pages, segments)

    def save(self, document_directory: Path, document: DocumentRecord) -> Path:
        del document_directory
        self._request_json(
            "POST",
            "documents",
            query={"on_conflict": "id"},
            body=[self._document_row(document)],
            prefer="resolution=merge-duplicates,return=minimal",
            expect_json=False,
        )
        self._delete_stale_page_rows(document)
        if document.pages:
            self._request_json(
                "POST",
                "document_pages",
                query={"on_conflict": "id"},
                body=[self._page_row(document, page) for page in document.pages],
                prefer="resolution=merge-duplicates,return=minimal",
                expect_json=False,
            )
        if document.audio_segments:
            self._request_json(
                "POST",
                "audio_segments",
                query={"on_conflict": "id"},
                body=[
                    self._audio_segment_row(document, segment)
                    for segment in document.audio_segments
                ],
                prefer="resolution=merge-duplicates,return=minimal",
                expect_json=False,
            )
        return Path(str(document.id))

    def delete(self, document_directory: Path) -> None:
        document_id = document_directory.name
        self._request_json(
            "DELETE",
            "documents",
            query={"id": f"eq.{document_id}"},
            expect_json=False,
        )

    def _list_related_rows(
        self,
        table: str,
        document_ids: list[str],
        order: str,
    ) -> list[dict[str, Any]]:
        if not document_ids:
            return []
        rows = self._request_json(
            "GET",
            table,
            query={
                "select": "*",
                "document_id": f"in.({','.join(document_ids)})",
                "order": order,
            },
        )
        if not isinstance(rows, list):
            raise self._invalid_response_error()
        return rows

    def _delete_related_rows(self, table: str, document_id: UUID) -> None:
        self._request_json(
            "DELETE",
            table,
            query={"document_id": f"eq.{document_id}"},
            expect_json=False,
        )

    def _delete_stale_page_rows(self, document: DocumentRecord) -> None:
        if not document.pages:
            self._delete_related_rows("document_pages", document.id)
            return

        current_page_ids = ",".join(str(page.id) for page in document.pages)
        self._request_json(
            "DELETE",
            "document_pages",
            query={
                "document_id": f"eq.{document.id}",
                "id": f"not.in.({current_page_ids})",
            },
            expect_json=False,
        )

    def _request_json(
        self,
        method: str,
        table: str,
        *,
        query: dict[str, str] | None = None,
        body: object | None = None,
        prefer: str | None = None,
        expect_json: bool = True,
    ) -> object | None:
        encoded_query = urllib.parse.urlencode(query or {})
        url = f"{self.rest_url}/{table}"
        if encoded_query:
            url = f"{url}?{encoded_query}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer is not None:
            headers["Prefer"] = prefer
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        max_attempts = 3 if method in self.transient_retry_methods else 1
        for attempt in range(max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    response_body = response.read()
                break
            except urllib.error.HTTPError as error:
                if (
                    error.code in self.transient_status_codes
                    and attempt < max_attempts - 1
                ):
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise EchoError(
                    "supabase_metadata_failed",
                    "Echo could not save or load your library information.",
                    status_code=502,
                    details={"status_code": error.code},
                ) from error
            except (
                urllib.error.URLError,
                TimeoutError,
                http.client.HTTPException,
            ) as error:
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise EchoError(
                    "supabase_metadata_unavailable",
                    "Echo could not reach the library database right now.",
                    status_code=503,
                ) from error

        if not expect_json:
            return None
        if not response_body:
            return None
        try:
            return json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise self._invalid_response_error() from error

    @staticmethod
    def _records_from_rows(
        document_rows: Iterable[object],
        page_rows: list[dict[str, Any]],
        segment_rows: list[dict[str, Any]],
    ) -> list[DocumentRecord]:
        pages_by_document: dict[str, list[dict[str, Any]]] = {}
        for page in page_rows:
            pages_by_document.setdefault(str(page["document_id"]), []).append(page)

        segments_by_document: dict[str, list[dict[str, Any]]] = {}
        for segment in segment_rows:
            segments_by_document.setdefault(str(segment["document_id"]), []).append(segment)

        return [
            SupabaseDocumentMetadataService._record_from_rows(
                document,
                pages_by_document.get(str(document["id"]), []),
                segments_by_document.get(str(document["id"]), []),
            )
            for document in document_rows
            if isinstance(document, dict)
        ]

    @staticmethod
    def _record_from_rows(
        document: dict[str, Any],
        pages: list[dict[str, Any]],
        segments: list[dict[str, Any]],
    ) -> DocumentRecord:
        return DocumentRecord.model_validate(
            {
                "id": document["id"],
                "library_book_id": document["library_document_id"],
                "user_id": document["user_id"],
                "title": document["title"],
                "recording_title": document["recording_title"],
                "target_language": document["target_language"],
                "tts_voice": document["tts_voice"],
                "original_filename": document["original_filename"],
                "source_type": document["source_type"],
                "source_storage_path": document["source_storage_path"],
                "total_pages": document["total_pages"],
                "status": document["status"],
                "error_message": document["error_message"],
                "pages": [
                    SupabaseDocumentMetadataService._page_record_payload(page)
                    for page in pages
                ],
                "audio_segments": [
                    SupabaseDocumentMetadataService._audio_segment_payload(segment)
                    for segment in segments
                ],
                "created_at": document["created_at"],
                "updated_at": document["updated_at"],
            }
        )

    @staticmethod
    def _page_record_payload(page: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": page["id"],
            "book_id": page["document_id"],
            "page_number": page["page_number"],
            "original_filename": page["original_filename"],
            "original_image_path": page["original_image_storage_path"],
            "processed_image_path": page["processed_image_storage_path"],
            "extraction_method": page["extraction_method"],
            "extracted_text": page["extracted_text"],
            "error_message": page["error_message"],
            "warning_messages": page.get("warning_messages") or [],
            "crop_left": page.get("crop_left"),
            "crop_top": page.get("crop_top"),
            "crop_right": page.get("crop_right"),
            "crop_bottom": page.get("crop_bottom"),
            "rotation_degrees": page["rotation_degrees"],
            "processing_status": page["processing_status"],
            "created_at": page["created_at"],
            "updated_at": page["updated_at"],
        }

    @staticmethod
    def _audio_segment_payload(segment: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": segment["id"],
            "book_id": segment["document_id"],
            "page_id": segment["page_id"],
            "segment_number": segment["segment_number"],
            "source_text": segment["source_text"],
            "audio_storage_path": segment["audio_storage_path"],
            "duration_seconds": segment["duration_seconds"],
            "processing_status": segment["processing_status"],
            "error_message": segment["error_message"],
            "created_at": segment["created_at"],
            "updated_at": segment["updated_at"],
        }

    @staticmethod
    def _document_row(document: DocumentRecord) -> dict[str, Any]:
        return {
            "id": str(document.id),
            "user_id": str(document.user_id) if document.user_id is not None else None,
            "library_document_id": (
                str(document.library_document_id)
                if document.library_document_id is not None
                else None
            ),
            "title": document.title,
            "recording_title": document.recording_title,
            "target_language": document.target_language,
            "tts_voice": document.tts_voice,
            "original_filename": document.original_filename,
            "source_type": document.source_type,
            "source_storage_path": document.source_storage_path,
            "total_pages": document.total_pages,
            "status": document.status,
            "error_message": document.error_message,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
        }

    @staticmethod
    def _page_row(
        document: DocumentRecord,
        page: DocumentPageRecord,
    ) -> dict[str, Any]:
        return {
            "id": str(page.id),
            "document_id": str(document.id),
            "user_id": str(document.user_id) if document.user_id is not None else None,
            "page_number": page.page_number,
            "original_filename": page.original_filename,
            "original_image_storage_path": page.original_image_path,
            "processed_image_storage_path": page.processed_image_path,
            "extraction_method": page.extraction_method,
            "extracted_text": page.extracted_text,
            "error_message": page.error_message,
            "warning_messages": page.warning_messages,
            "crop_left": page.crop_left,
            "crop_top": page.crop_top,
            "crop_right": page.crop_right,
            "crop_bottom": page.crop_bottom,
            "rotation_degrees": page.rotation_degrees,
            "processing_status": page.processing_status,
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }

    @staticmethod
    def _audio_segment_row(
        document: DocumentRecord,
        segment: AudioSegmentRecord,
    ) -> dict[str, Any]:
        return {
            "id": str(segment.id),
            "document_id": str(document.id),
            "user_id": str(document.user_id) if document.user_id is not None else None,
            "page_id": str(segment.page_id) if segment.page_id is not None else None,
            "segment_number": segment.segment_number,
            "source_text": segment.source_text,
            "audio_storage_path": segment.audio_storage_path,
            "duration_seconds": segment.duration_seconds,
            "processing_status": segment.processing_status,
            "error_message": segment.error_message,
            "created_at": segment.created_at.isoformat(),
            "updated_at": segment.updated_at.isoformat(),
        }

    @staticmethod
    def _invalid_response_error() -> EchoError:
        return EchoError(
            "supabase_metadata_invalid",
            "Echo could not read the library database response.",
            status_code=502,
        )
