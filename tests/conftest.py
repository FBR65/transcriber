"""Gemeinsame Helfer: WAV-Dateien, Test-Adapter, Registry."""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Sequence
from pathlib import Path

import pytest

from transcriber import AsrSegment, SpeakerTurn
from transcriber.registry import DEFAULT_REGISTRY, Registry


def write_wav(
    path: Path,
    seconds: float = 2.0,
    rate: int = 16000,
    channels: int = 1,
    amplitude: float = 0.3,
) -> Path:
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        data = bytearray()
        for index in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * index / rate))
            for _ in range(channels):
                data += struct.pack("<h", value)
        handle.writeframes(bytes(data))
    return path


class FakeAsr:
    def __init__(self, segments: Sequence[AsrSegment]) -> None:
        self.segments = list(segments)

    def transcribe(self, path: Path, options: object | None = None) -> list[AsrSegment]:
        return list(self.segments)


class FakeDiarizer:
    def __init__(self, turns: Sequence[SpeakerTurn]) -> None:
        self.turns = list(turns)

    def diarize(self, path: Path, options: object | None = None) -> list[SpeakerTurn]:
        return list(self.turns)


class FakeLanguageId:
    def __init__(self, language: str = "de", confidence: float = 0.9) -> None:
        self.language = language
        self.confidence = confidence

    def detect(self, path: Path, start_s: float, end_s: float) -> tuple[str, float]:
        return self.language, self.confidence


class FakeTranslator:
    """Markiert jede Übersetzung, damit ein Tausch sichtbar wird."""

    def __init__(self, marker: str = "translated", languages: Sequence[str] | None = None) -> None:
        self.marker = marker
        self._languages = set(languages or ("de", "en", "fr", "es"))

    def languages(self) -> set[str]:
        return set(self._languages)

    def translate(
        self, texts: Sequence[str], source_lang: str, target_lang: str
    ) -> list[str]:
        return [f"[{self.marker}:{target_lang}] {text}" for text in texts]


TWO_SPEAKERS = [
    AsrSegment(0.0, 1.0, "Hallo Welt", "de"),
    AsrSegment(1.0, 2.0, "Hello world", "en"),
]
ONE_SPEAKER = [AsrSegment(0.0, 2.0, "Hallo Welt", "de")]
TURNS_TWO = [SpeakerTurn(0.0, 1.0, "S1"), SpeakerTurn(1.0, 2.0, "S2")]


class FakeVoiceprint:
    """Nimmt einen festen Vektor je Tonabschnitt. Die Galerie ist echt."""

    def __init__(self, gallery: str | None = None, threshold: float = 0.70) -> None:
        from transcriber.gallery import Gallery

        self._gallery = Gallery(gallery, threshold=threshold)

    def _embedding(self, path: Path, start_s: float, end_s: float) -> object:
        import hashlib

        digest = hashlib.sha256(f"{path.name}:{start_s:.2f}".encode()).digest()
        values = [byte + 1 for byte in digest[:8]]
        return [value / 1000.0 for value in values]

    def identify(self, path: Path, start_s: float, end_s: float) -> object:
        import numpy as np

        return self._gallery.match(np.asarray(self._embedding(path, start_s, end_s)))

    def enroll(
        self, path: Path, start_s: float, end_s: float, name: str, *, consent: bool
    ) -> object:
        import numpy as np

        return self._gallery.add(
            name, np.asarray(self._embedding(path, start_s, end_s)), consent=consent
        )

    def delete(self, reference: str) -> int:
        return self._gallery.delete(reference)

    def people(self) -> list[object]:
        return list(self._gallery.people())


def register_fake_adapters(reg: Registry) -> None:
    reg.register("asr", "fake", lambda: FakeAsr(TWO_SPEAKERS))
    reg.register("asr", "single", lambda: FakeAsr(ONE_SPEAKER))
    reg.register("asr", "empty", lambda: FakeAsr([]))
    reg.register("diarizer", "fake", lambda: FakeDiarizer(TURNS_TWO))
    reg.register("diarizer", "one", lambda: FakeDiarizer([SpeakerTurn(0.0, 2.0, "S1")]))
    reg.register("language_id", "fake", lambda: FakeLanguageId())
    reg.register("translator", "fake", lambda: FakeTranslator("translated"))
    reg.register("translator", "upper", lambda: FakeTranslator("upper"))
    reg.register("voiceprint", "fake", FakeVoiceprint)


@pytest.fixture(autouse=True)
def fake_adapters() -> None:
    register_fake_adapters(DEFAULT_REGISTRY)


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "probe.wav")
