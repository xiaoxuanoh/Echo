from dataclasses import dataclass
import re
import unicodedata
from uuid import UUID

from app.models.documents import DocumentPageRecord

CJK_RADICAL_REPLACEMENTS = {
    "⻑": "長",
}


@dataclass(frozen=True)
class TextSegmentDraft:
    page_id: UUID
    page_number: int
    source_text: str


class TextSegmentationService:
    """Splits prepared page text into ordered chunks suitable for speech."""

    def __init__(
        self,
        max_characters: int,
        *,
        target_seconds: int = 360,
        soft_max_seconds: int = 420,
        min_seconds: int = 30,
    ) -> None:
        self.max_characters = max_characters
        self.target_seconds = target_seconds
        self.soft_max_seconds = soft_max_seconds
        self.min_seconds = min_seconds

    def segment_pages(self, pages: list[DocumentPageRecord]) -> list[TextSegmentDraft]:
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
        paragraphs = self._normalize_paragraphs(self._normalize_cjk_lookalikes(text))
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
        return self._merge_short_final_chunk(chunks)

    def _normalize_paragraphs(self, text: str) -> list[str]:
        paragraphs: list[str] = []
        current_lines: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current_lines:
                    paragraphs.append(self._join_visual_lines(current_lines))
                    current_lines = []
                continue

            if self._is_probable_heading(stripped):
                if current_lines:
                    paragraphs.append(self._join_visual_lines(current_lines))
                    current_lines = []
                paragraphs.append(stripped)
            else:
                current_lines.append(stripped)

        if current_lines:
            paragraphs.append(self._join_visual_lines(current_lines))

        if not paragraphs and text.strip():
            paragraphs.append(text.strip())

        cleaned_paragraphs = [
            self._remove_cjk_whitespace(paragraph) for paragraph in paragraphs
        ]
        merged_paragraphs = self._merge_broken_cjk_fragments(cleaned_paragraphs)
        return self._attach_headings_to_following_paragraphs(merged_paragraphs)

    def _normalize_cjk_lookalikes(self, text: str) -> str:
        output = []
        for character in text:
            replacement = CJK_RADICAL_REPLACEMENTS.get(character)
            if replacement is not None:
                output.append(replacement)
                continue

            code_point = ord(character)
            if (
                0x2E80 <= code_point <= 0x2EFF
                or 0x2F00 <= code_point <= 0x2FDF
                or 0xF900 <= code_point <= 0xFAFF
            ):
                output.append(unicodedata.normalize("NFKC", character))
                continue

            output.append(character)
        return "".join(output)

    def _join_visual_lines(self, lines: list[str]) -> str:
        if not lines:
            return ""

        text = lines[0]
        for line in lines[1:]:
            separator = "" if self._should_join_without_space(text, line) else " "
            text = f"{text}{separator}{line}"
        return text

    def _should_join_without_space(self, previous: str, next_line: str) -> bool:
        previous_character = previous.rstrip()[-1:]
        next_character = next_line.lstrip()[:1]
        return self._is_cjk(previous_character) and self._is_cjk(next_character)

    def _remove_cjk_whitespace(self, text: str) -> str:
        output = []
        index = 0
        while index < len(text):
            character = text[index]
            if character.isspace():
                previous_character = output[-1] if output else ""
                next_character = self._next_non_space_character(text, index + 1)
                if self._is_cjk(previous_character) and self._is_cjk(next_character):
                    index += 1
                    continue
                output.append(" ")
                index += 1
                continue
            output.append(character)
            index += 1
        return "".join(output)

    def _merge_broken_cjk_fragments(self, paragraphs: list[str]) -> list[str]:
        merged: list[str] = []
        for paragraph in paragraphs:
            if (
                merged
                and self._is_short_cjk_fragment(paragraph)
                and self._can_merge_with_previous_paragraph(merged[-1], paragraph)
            ):
                merged[-1] = f"{merged[-1]}{paragraph}"
            else:
                merged.append(paragraph)
        return merged

    def _attach_headings_to_following_paragraphs(
        self, paragraphs: list[str]
    ) -> list[str]:
        attached: list[str] = []
        pending_heading: str | None = None

        for paragraph in paragraphs:
            if self._is_probable_heading(paragraph):
                if pending_heading is not None:
                    attached.append(pending_heading)
                pending_heading = paragraph
                continue

            if pending_heading is not None:
                attached.append(f"{pending_heading}\n\n{paragraph}")
                pending_heading = None
            else:
                attached.append(paragraph)

        if pending_heading is not None:
            attached.append(pending_heading)

        return attached

    def _is_short_cjk_fragment(self, text: str) -> bool:
        cjk_count = sum(self._is_cjk(character) for character in text)
        return 0 < cjk_count <= 8 and cjk_count >= len(text.strip()) / 2

    def _can_merge_with_previous_paragraph(self, previous: str, next_paragraph: str) -> bool:
        if self._is_probable_heading(previous):
            return False
        previous_character = previous.rstrip()[-1:]
        next_character = next_paragraph.lstrip()[:1]
        if not (self._is_cjk(previous_character) and self._is_cjk(next_character)):
            return False
        return previous_character not in "。！？!?"

    def _next_non_space_character(self, text: str, start: int) -> str:
        for character in text[start:]:
            if not character.isspace():
                return character
        return ""

    def _is_probable_heading(self, line: str) -> bool:
        if len(line) > 40:
            return False
        if line[-1:] in "。！？!?；;，,、：:":
            return False
        if line.startswith(("「", "《")):
            return True
        return False

    def _is_cjk(self, character: str) -> bool:
        if not character:
            return False
        code_point = ord(character)
        return (
            0x2E80 <= code_point <= 0x2EFF
            or 0x2F00 <= code_point <= 0x2FDF
            or 0x3400 <= code_point <= 0x4DBF
            or 0x4E00 <= code_point <= 0x9FFF
            or 0xF900 <= code_point <= 0xFAFF
        )

    def _split_long_piece(self, text: str) -> list[str]:
        if (
            len(text) <= self.max_characters
            and self._estimate_spoken_seconds(text) <= self.soft_max_seconds
        ):
            return [text]

        pieces: list[str] = []
        remaining = text
        sentence_marks = "。！？!?；;."
        while (
            len(remaining) > self.max_characters
            or self._estimate_spoken_seconds(remaining) > self.soft_max_seconds
        ):
            limit_index = self._target_split_index(remaining)
            window = remaining[: limit_index + 1]
            split_at = max(window.rfind(mark) for mark in sentence_marks)
            if split_at < max(1, limit_index // 2):
                split_at = limit_index
            else:
                split_at += 1
            pieces.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()

        if remaining:
            pieces.append(remaining)
        return self._merge_short_final_chunk([piece for piece in pieces if piece])

    def _target_split_index(self, text: str) -> int:
        char_limit = min(self.max_characters, len(text))
        best = 1
        low = 1
        high = char_limit
        while low <= high:
            midpoint = (low + high) // 2
            if self._estimate_spoken_seconds(text[:midpoint]) <= self.target_seconds:
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        return best

    def _merge_short_final_chunk(self, chunks: list[str]) -> list[str]:
        if len(chunks) < 2:
            return chunks

        final_chunk = chunks[-1]
        if self._estimate_spoken_seconds(final_chunk) >= self.min_seconds:
            return chunks

        candidate = f"{chunks[-2]}\n\n{final_chunk}"
        if (
            len(candidate) <= self.max_characters
            and self._estimate_spoken_seconds(candidate) <= self.soft_max_seconds
        ):
            return [*chunks[:-2], candidate]
        return chunks

    def _estimate_spoken_seconds(self, text: str) -> float:
        cjk_count = sum(self._is_cjk(character) for character in text)
        latin_word_count = len(
            re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?", text)
        )
        other_spoken_count = sum(
            1
            for character in text
            if (
                not character.isspace()
                and not self._is_cjk(character)
                and not character.isascii()
            )
        )
        pause_count = sum(character in "。！？!?；;，,、：:." for character in text)
        return (
            cjk_count / 3.8
            + latin_word_count / 2.6
            + other_spoken_count / 3.2
            + pause_count * 0.2
        )
