import math
import wave
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.errors import EchoError


DEFAULT_AZURE_SPEECH_VOICE = "zh-HK-HiuMaanNeural"


class TtsProvider(Protocol):
    """Creates one playable audio file from one text segment."""

    def synthesize(self, text: str, destination: Path) -> float:
        """Write audio to destination and return the best-known duration."""


class MockTtsProvider:
    """Creates local placeholder WAV files so playback can be tested for free."""

    sample_rate = 16_000

    def synthesize(self, text: str, destination: Path) -> float:
        destination.parent.mkdir(parents=True, exist_ok=True)
        duration_seconds = self._duration_for_text(text)
        frame_count = int(duration_seconds * self.sample_rate)

        with wave.open(str(destination), "wb") as audio_file:
            audio_file.setnchannels(1)
            audio_file.setsampwidth(2)
            audio_file.setframerate(self.sample_rate)
            audio_file.writeframes(self._tone_frames(frame_count))

        return duration_seconds

    def _duration_for_text(self, text: str) -> float:
        return min(8.0, max(1.2, len(text.strip()) / 35))

    def _tone_frames(self, frame_count: int) -> bytes:
        frames = bytearray()
        frequency = 440
        amplitude = 1800
        for index in range(frame_count):
            sample = int(
                amplitude * math.sin(2 * math.pi * frequency * index / self.sample_rate)
            )
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        return bytes(frames)


class AzureSpeechTtsProvider:
    """Creates real speech audio with Azure Speech Service."""

    def __init__(self, *, speech_key: str, region: str, voice: str) -> None:
        self.speech_key = speech_key.strip()
        self.region = region.strip()
        self.voice = voice.strip() or DEFAULT_AZURE_SPEECH_VOICE

        missing = [
            name
            for name, value in {
                "AZURE_SPEECH_KEY": self.speech_key,
                "AZURE_SPEECH_REGION": self.region,
                "AZURE_SPEECH_VOICE": self.voice,
            }.items()
            if not value
        ]
        if missing:
            raise EchoError(
                "tts_configuration_missing",
                "Real speech is selected, but Azure Speech is not fully configured.",
                status_code=500,
                details={"missing": missing},
            )

    def synthesize(self, text: str, destination: Path) -> float:
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as error:
            raise EchoError(
                "tts_dependency_missing",
                "Real speech is selected, but the Azure Speech SDK is not installed.",
                status_code=500,
            ) from error

        destination.parent.mkdir(parents=True, exist_ok=True)

        speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key,
            region=self.region,
        )
        speech_config.speech_synthesis_voice_name = self.voice
        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(destination))
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        result = synthesizer.speak_text_async(text).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return self._duration_seconds(result, text)

        if result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            reason = str(details.reason)
            message = "Azure Speech could not create audio for this segment."
            if details.error_details:
                message = f"{message} {details.error_details}"
            raise EchoError(
                "tts_synthesis_failed",
                message,
                status_code=502,
                details={"reason": reason},
            )

        raise EchoError(
            "tts_synthesis_failed",
            "Azure Speech returned an unexpected synthesis result.",
            status_code=502,
            details={"reason": str(result.reason)},
        )

    def _duration_seconds(self, result: object, text: str) -> float:
        audio_duration = getattr(result, "audio_duration", None)
        if audio_duration is not None:
            try:
                return max(0.0, float(audio_duration.total_seconds()))
            except (AttributeError, TypeError, ValueError):
                pass
        return min(120.0, max(1.0, len(text.strip()) / 6))


def create_tts_provider(settings: Settings) -> TtsProvider:
    if settings.use_mock_tts:
        return MockTtsProvider()
    return AzureSpeechTtsProvider(
        speech_key=settings.azure_speech_key,
        region=settings.azure_speech_region,
        voice=settings.azure_speech_voice,
    )
