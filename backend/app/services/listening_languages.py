from typing import Literal

from app.core.errors import EchoError


ListeningLanguage = Literal["cantonese", "mandarin", "english"]


LANGUAGE_VOICES: dict[ListeningLanguage, str] = {
    "cantonese": "zh-HK-HiuMaanNeural",
    "mandarin": "zh-CN-XiaoxiaoNeural",
    "english": "en-US-JennyNeural",
}


LANGUAGE_LABELS: dict[ListeningLanguage, str] = {
    "cantonese": "Cantonese",
    "mandarin": "Mandarin",
    "english": "English",
}


def resolve_listening_language(value: str | None) -> ListeningLanguage | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in LANGUAGE_VOICES:
        raise EchoError(
            "target_language_unknown",
            "Choose Cantonese, Mandarin, or English before uploading.",
            status_code=422,
            details={"target_language": value},
        )
    return normalized  # type: ignore[return-value]


def voice_for_language(language: ListeningLanguage | None) -> str | None:
    if language is None:
        return None
    return LANGUAGE_VOICES[language]
