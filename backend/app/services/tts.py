import json
import math
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.errors import EchoError


DEFAULT_AZURE_SPEECH_VOICE = "zh-HK-HiuMaanNeural"


class TtsProvider(Protocol):
    """Creates one playable audio file from one text segment."""

    audio_file_extension: str
    media_type: str

    def synthesize(self, text: str, destination: Path) -> float:
        """Write audio to destination and return the best-known duration."""


class MockTtsProvider:
    """Creates local placeholder WAV files so playback can be tested for free."""

    audio_file_extension = "wav"
    media_type = "audio/wav"
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

    audio_file_extension = "wav"
    media_type = "audio/wav"

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


class ElevenLabsTtsProvider:
    """Creates real speech audio with ElevenLabs Text to Speech."""

    audio_file_extension = "mp3"
    media_type = "audio/mpeg"

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str,
        output_format: str,
    ) -> None:
        self.api_key = api_key.strip()
        self.voice_id = voice_id.strip()
        self.model_id = model_id.strip() or "eleven_multilingual_v2"
        self.output_format = output_format.strip() or "mp3_44100_128"

        missing = [
            name
            for name, value in {
                "ELEVENLABS_API_KEY": self.api_key,
                "ELEVENLABS_VOICE_ID": self.voice_id,
                "ELEVENLABS_MODEL_ID": self.model_id,
            }.items()
            if not value
        ]
        if missing:
            raise EchoError(
                "tts_configuration_missing",
                "ElevenLabs speech is selected, but ElevenLabs is not fully configured.",
                status_code=500,
                details={"missing": missing},
            )

    def synthesize(self, text: str, destination: Path) -> float:
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded_voice_id = urllib.parse.quote(self.voice_id, safe="")
        query = urllib.parse.urlencode({"output_format": self.output_format})
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{encoded_voice_id}?{query}"
        payload = json.dumps(
            {
                "text": text,
                "model_id": self.model_id,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Accept": self.media_type,
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                destination.write_bytes(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise EchoError(
                "tts_synthesis_failed",
                "ElevenLabs could not create audio for this segment.",
                status_code=502,
                details={"provider_status": error.code, "provider_error": detail},
            ) from error
        except urllib.error.URLError as error:
            raise EchoError(
                "tts_synthesis_failed",
                "Echo could not reach ElevenLabs to create audio.",
                status_code=502,
                details={"reason": str(error.reason)},
            ) from error

        return min(120.0, max(1.0, len(text.strip()) / 6))


def create_tts_provider(settings: Settings) -> TtsProvider:
    if settings.use_mock_tts:
        return MockTtsProvider()
    provider_name = settings.tts_provider.lower().strip()
    if provider_name == "elevenlabs":
        return ElevenLabsTtsProvider(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
            output_format=settings.elevenlabs_output_format,
        )
    if provider_name != "azure":
        raise EchoError(
            "tts_provider_unknown",
            "Echo does not recognize the selected speech provider.",
            status_code=500,
            details={"tts_provider": settings.tts_provider},
        )
    return AzureSpeechTtsProvider(
        speech_key=settings.azure_speech_key,
        region=settings.azure_speech_region,
        voice=settings.azure_speech_voice,
    )
