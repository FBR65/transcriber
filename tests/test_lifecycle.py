"""Adapter werden je Stufe erzeugt und danach freigegeben (SPEC Abschnitt 11)."""

from __future__ import annotations

from pathlib import Path

from transcriber import AsrSegment, Registry, RunConfig, SpeakerTurn, run_file

from .conftest import write_wav

EVENTS: list[str] = []


class Recording:
    def __init__(self, name: str) -> None:
        self.name = name

    def release(self) -> None:
        EVENTS.append(f"{self.name}:release")


class RecAsr(Recording):
    def __init__(self) -> None:
        super().__init__("asr")

    def transcribe(self, path: Path, options: object | None = None) -> list[AsrSegment]:
        EVENTS.append("asr:work")
        return [AsrSegment(0.0, 1.0, "Hallo", "de")]


class RecDiarizer(Recording):
    def __init__(self) -> None:
        super().__init__("diarizer")

    def diarize(self, path: Path, options: object | None = None) -> list[SpeakerTurn]:
        EVENTS.append("diarizer:work")
        return [SpeakerTurn(0.0, 1.0, "S1")]


class RecLanguageId(Recording):
    def __init__(self) -> None:
        super().__init__("language_id")

    def detect(self, path: Path, start_s: float, end_s: float) -> tuple[str, float]:
        EVENTS.append("language_id:work")
        return "de", 0.9


class RecTranslator(Recording):
    def __init__(self) -> None:
        super().__init__("translator")

    def languages(self) -> set[str]:
        return {"de", "fr"}

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        EVENTS.append("translator:work")
        return [f"[{target}] {text}" for text in texts]


def test_adapters_are_released_stage_by_stage(tmp_path: Path) -> None:
    EVENTS.clear()
    registry = Registry()
    registry.register("asr", "rec", RecAsr)
    registry.register("diarizer", "rec", RecDiarizer)
    registry.register("language_id", "rec", RecLanguageId)
    registry.register("translator", "rec", RecTranslator)

    audio = write_wav(tmp_path / "ton.wav")
    run_file(
        audio,
        config=RunConfig(
            asr="rec",
            diarizer="rec",
            language_id="rec",
            translator="rec",
            target_languages=["fr"],
        ),
        registry=registry,
    )

    assert EVENTS == [
        "asr:work",
        "asr:release",
        "diarizer:work",
        "diarizer:release",
        "translator:work",
        "translator:release",
    ]


class RecAsrWithoutLanguage(RecAsr):
    def transcribe(self, path: Path, options: object | None = None) -> list[AsrSegment]:
        EVENTS.append("asr:work")
        return [AsrSegment(0.0, 1.0, "Hallo")]


def test_language_id_runs_only_when_asr_gives_no_language(tmp_path: Path) -> None:
    EVENTS.clear()
    registry = Registry()
    registry.register("asr", "rec", RecAsrWithoutLanguage)
    registry.register("diarizer", "rec", RecDiarizer)
    registry.register("language_id", "rec", RecLanguageId)
    registry.register("translator", "rec", RecTranslator)

    audio = write_wav(tmp_path / "ohne-sprache.wav")
    transcript = run_file(
        audio,
        config=RunConfig(
            asr="rec",
            diarizer="rec",
            language_id="rec",
            translator="rec",
            target_languages=["de"],
        ),
        registry=registry,
    )

    assert "language_id:work" in EVENTS
    assert transcript.segments[0].language == "de"
