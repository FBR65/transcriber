"""S1–S6, S11, S12: Kernverhalten."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcriber import (
    Registry,
    RunConfig,
    UnknownAdapterError,
    UnsupportedLanguageError,
    run_file,
)
from transcriber.core import assign_speakers

from .conftest import register_fake_adapters


def config(**overrides: object) -> RunConfig:
    base: dict[str, object] = {
        "asr": "fake",
        "diarizer": "fake",
        "language_id": "fake",
        "translator": "fake",
        "voiceprint": None,
        "target_languages": ["de"],
    }
    base.update(overrides)
    return RunConfig(**base)  # type: ignore[arg-type]


def test_single_speaker_same_language(audio_file: Path) -> None:
    result = run_file(
        audio_file, config=config(asr="single", diarizer="one"), registry=DEFAULT()
    )
    assert [speaker.id for speaker in result.speakers] == ["S1"]
    segment = result.segments[0]
    assert segment.translations["de"] == segment.text
    assert segment.translated_from is None
    assert segment.language == "de"


def test_two_speakers_assigned(audio_file: Path) -> None:
    result = run_file(audio_file, config=config(), registry=DEFAULT())
    speakers = [segment.speaker for segment in result.segments]
    assert set(speakers) == {"S1", "S2"}
    assert speakers == ["S1", "S2"]
    assert [segment.start_s for segment in result.segments] == sorted(
        segment.start_s for segment in result.segments
    )


def test_multilingual_translation(audio_file: Path) -> None:
    result = run_file(audio_file, config=config(target_languages=["fr"]), registry=DEFAULT())
    for segment in result.segments:
        assert set(segment.translations) == {"fr"}
        assert segment.translations["fr"].startswith("[translated:fr]")
        assert segment.translated_from == segment.language


def test_unsupported_target_language(audio_file: Path) -> None:
    with pytest.raises(UnsupportedLanguageError) as error:
        run_file(audio_file, config=config(target_languages=["xx"]), registry=DEFAULT())
    assert error.value.exit_code == 2


def test_unknown_adapter_name(audio_file: Path) -> None:
    with pytest.raises(UnknownAdapterError) as error:
        run_file(audio_file, config=config(asr="does-not-exist"), registry=DEFAULT())
    assert "fake" in error.value.available
    assert "single" in error.value.available


def test_adapter_swap_translator(audio_file: Path) -> None:
    result = run_file(audio_file, config=config(translator="upper"), registry=DEFAULT())
    # Segment 2 ist englisch, Ziel ist Deutsch: der getauschte Adapter muss wirken.
    assert result.segments[1].translations["de"].startswith("[upper:de]")
    # Segment 1 ist schon deutsch: SPEC S1 verlangt den unveränderten Text.
    assert result.segments[0].translations["de"] == result.segments[0].text
    assert result.model_dump(mode="json")["schema_version"] == 1


def test_deterministic_output(audio_file: Path) -> None:
    first = run_file(audio_file, config=config(target_languages=["fr"]), registry=DEFAULT())
    second = run_file(audio_file, config=config(target_languages=["fr"]), registry=DEFAULT())
    assert first.to_dict() | {"created_at": None} == second.to_dict() | {"created_at": None}


def test_overlap_assignment_rule() -> None:
    turns = [(0.0, 4.0, "S1"), (4.0, 10.0, "S2")]
    assert assign_speakers(0.0, 10.0, turns) == "S2"
    assert assign_speakers(6.0, 9.0, turns) == "S2"
    assert assign_speakers(0.0, 5.0, turns) == "S1"


def DEFAULT() -> Registry:
    registry = Registry()
    register_fake_adapters(registry)
    return registry
