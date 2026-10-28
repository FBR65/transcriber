"""Zweige, die nur mit bestimmten Adaptern auftreten."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from transcriber import AsrSegment, Registry, RunConfig, SpeakerTurn, i18n, run_file
from transcriber.core import assign_speakers

from .conftest import FakeLanguageId, register_fake_adapters, write_wav


class NoLanguageAsr:
    """ASR ohne Sprachangabe: der Kern muss die Sprach-ID fragen."""

    def transcribe(self, path: Path, options: object | None = None) -> list[AsrSegment]:
        return [AsrSegment(0.0, 1.0, "Hallo")]


class ShortTranslator:
    def languages(self) -> set[str]:
        return {"de", "en", "fr"}

    def translate(self, texts: Sequence[str], source: str, target: str) -> list[str]:
        return []


def build(registry: Registry) -> Registry:
    register_fake_adapters(registry)
    registry.register("asr", "nolang", NoLanguageAsr)
    registry.register("translator", "short", ShortTranslator)
    registry.register("language_id", "de", lambda: FakeLanguageId("de", 0.42))
    registry.register("diarizer", "leer", EmptyDiarizer)
    return registry


def base_config(**overrides: object) -> RunConfig:
    values: dict[str, object] = {
        "asr": "fake",
        "diarizer": "one",
        "language_id": "fake",
        "translator": "fake",
        "voiceprint": None,
        "target_languages": ["de"],
    }
    values.update(overrides)
    return RunConfig(**values)  # type: ignore[arg-type]


def test_assign_speakers_without_turns() -> None:
    assert assign_speakers(0.0, 1.0, []) is None


def test_language_id_is_asked_when_asr_has_none(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ohne-sprache.wav")
    result = run_file(
        audio, config=base_config(asr="nolang", language_id="de"), registry=build(Registry())
    )
    assert result.segments[0].language == "de"
    assert result.segments[0].language_confidence == pytest.approx(0.42)


def test_translator_with_wrong_count_is_rejected(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "kurz.wav")
    with pytest.raises(ValueError):
        run_file(
            audio,
            config=base_config(asr="fake", translator="short", target_languages=["fr"]),
            registry=build(Registry()),
        )


def test_diarizer_without_turns_gets_one_speaker(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ohne-diarizer.wav")
    result = run_file(
        audio, config=base_config(diarizer="leer"), registry=build(Registry())
    )
    assert [speaker.id for speaker in result.speakers] == ["S1"]


def test_catalog_must_be_an_object(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "xx.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    monkeypatch.setattr(i18n, "CATALOG_DIR", tmp_path)
    i18n.catalog.cache_clear()
    with pytest.raises(TypeError):
        i18n.catalog("xx")
    i18n.catalog.cache_clear()


class EmptyDiarizer:
    def diarize(self, path: Path, options: object | None = None) -> list[SpeakerTurn]:
        return []
