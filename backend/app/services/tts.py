import math
import wave
from pathlib import Path


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
