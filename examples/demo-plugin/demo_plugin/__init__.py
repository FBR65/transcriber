"""Beispiel-Plug-in. Beweist den Einstiegspunkt `transcriber.adapters` ohne ML-Modelle.

Die Adapter liefern feste Daten. Damit lässt sich der ganze Weg prüfen:
Datei → ffprobe → Kern → Export. Ein echter Lauf mit Modellen folgt in P1.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from transcriber.ports import AsrSegment, SpeakerTurn
from transcriber.registry import Registry

SEGMENTS = (
    AsrSegment(0.0, 1.2, "Guten Tag, hier spricht Sprecher eins.", "de"),
    AsrSegment(1.2, 2.4, "And here is the second speaker.", "en"),
    AsrSegment(2.4, 3.0, "Zum Schluss wieder deutsch.", "de"),
)


class DemoAsr:
    def transcribe(self, path: Path, options: object | None = None) -> Sequence[AsrSegment]:
        return SEGMENTS


class DemoDiarizer:
    def diarize(self, path: Path, options: object | None = None) -> Sequence[SpeakerTurn]:
        return (
            SpeakerTurn(0.0, 1.2, "SPEAKER_00"),
            SpeakerTurn(1.2, 2.4, "SPEAKER_01"),
            SpeakerTurn(2.4, 3.0, "SPEAKER_00"),
        )


class DemoLanguageId:
    def detect(self, path: Path, start_s: float, end_s: float) -> tuple[str, float]:
        return "de", 0.5


class DemoTranslator:
    def languages(self) -> set[str]:
        return {"de", "en", "fr", "es"}

    def translate(self, texts: Sequence[str], source_lang: str, target_lang: str) -> list[str]:
        return [f"<{target_lang}>{text}" for text in texts]


def register(registry: Registry) -> None:
    registry.register("asr", "demo", DemoAsr)
    registry.register("diarizer", "demo", DemoDiarizer)
    registry.register("language_id", "demo", DemoLanguageId)
    registry.register("translator", "demo", DemoTranslator)
