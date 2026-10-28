"""Lücken, die die Mutantenprüfung sichtbar gemacht hat."""

from __future__ import annotations

import json
import re
from pathlib import Path

from transcriber import Registry, RunConfig, export, run_file
from transcriber.core import assign_speakers

from .conftest import register_fake_adapters


def test_assign_speakers_tie_goes_to_earliest_start() -> None:
    """Gleichstand: frühester Beginn gewinnt, nicht der nächste Mittelpunkt."""
    turns = [(0.0, 10.0, "S1"), (0.0, 1.0, "S2")]
    assert assign_speakers(0.0, 0.5, turns) == "S1"


def test_speaker_counts_and_speech_time(audio_file: Path) -> None:
    registry = Registry()
    register_fake_adapters(registry)
    result = run_file(
        audio_file,
        config=RunConfig(
            asr="fake",
            diarizer="fake",
            language_id="fake",
            translator="fake",
            target_languages=["de"],
        ),
        registry=registry,
    )
    counts = {speaker.id: speaker.segment_count for speaker in result.speakers}
    assert counts == {"S1": 1, "S2": 1}
    speech = {speaker.id: speaker.speech_s for speaker in result.speakers}
    assert speech == {"S1": 1.0, "S2": 1.0}


def test_json_export_is_byte_stable(audio_file: Path, tmp_path: Path) -> None:
    registry = Registry()
    register_fake_adapters(registry)
    transcript = run_file(
        audio_file,
        config=RunConfig(
            asr="fake",
            diarizer="fake",
            language_id="fake",
            translator="fake",
            target_languages=["de"],
        ),
        registry=registry,
    )
    first = export(transcript, tmp_path / "a", formats=("json",))[0]
    second = export(transcript, tmp_path / "b", formats=("json",))[0]
    assert first.read_bytes() == second.read_bytes()
    text = first.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_docs_heading_levels_match() -> None:
    root = Path(__file__).resolve().parents[1]

    def levels(path: Path) -> list[int]:
        text = path.read_text(encoding="utf-8")
        return [len(match.group(1)) for match in re.finditer(r"^(#{1,6}) .+$", text, re.M)]

    assert levels(root / "README.md") == levels(root / "README.de.md")
