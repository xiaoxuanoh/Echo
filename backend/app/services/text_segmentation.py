from dataclasses import dataclass
from uuid import UUID

from app.models.books import BookPageRecord


@dataclass(frozen=True)
class TextSegmentDraft:
    page_id: UUID
    page_number: int
    source_text: str


class TextSegmentationService:
    """Splits prepared page text into ordered chunks suitable for speech."""

    def __init__(self, max_characters: int) -> None:
        self.max_characters = max_characters

    def segment_pages(self, pages: list[BookPageRecord]) -> list[TextSegmentDraft]:
        segments: list[TextSegmentDraft] = []
        for page in sorted(pages, key=lambda item: item.page_number):
            text = page.extracted_text.strip()
            if not text:
                continue
            for chunk in self._split_text(text):
                segments.append(
                    TextSegmentDraft(
                        page_id=page.id,
                        page_number=page.page_number,
                        source_text=chunk,
                    )
                )
        return segments

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [item.strip() for item in text.splitlines() if item.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs or [text.strip()]:
            for piece in self._split_long_piece(paragraph):
                if not current:
                    current = piece
                    continue
                candidate = f"{current}\n\n{piece}"
                if len(candidate) <= self.max_characters:
                    current = candidate
                else:
                    chunks.append(current)
                    current = piece

        if current:
            chunks.append(current)
        return chunks

    def _split_long_piece(self, text: str) -> list[str]:
        if len(text) <= self.max_characters:
            return [text]

        pieces: list[str] = []
        remaining = text
        sentence_marks = "。！？!?；;."
        while len(remaining) > self.max_characters:
            window = remaining[: self.max_characters + 1]
            split_at = max(window.rfind(mark) for mark in sentence_marks)
            if split_at < max(1, self.max_characters // 2):
                split_at = self.max_characters
            else:
                split_at += 1
            pieces.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()

        if remaining:
            pieces.append(remaining)
        return [piece for piece in pieces if piece]
