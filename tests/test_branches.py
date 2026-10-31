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


def test_smooth_languages_lends_the_nearest_confident_language() -> None:
    from transcriber.core import Draft, smooth_languages

    drafts = [
        Draft(1, 0.0, 1.0, "S1", "nl", 0.29, "Hallo"),
        Draft(2, 1.0, 4.0, "S1", "de", 0.99, "Guten Tag"),
        Draft(3, 4.0, 4.4, "S2", "kk", 0.19, "Ja"),
        Draft(4, 4.4, 8.0, "S2", "de", 1.00, "Auf Wiedersehen"),
    ]
    smooth_languages(drafts)
    assert [draft.language for draft in drafts] == ["de", "de", "de", "de"]


def test_smooth_languages_keeps_everything_when_nothing_is_confident() -> None:
    from transcriber.core import Draft, smooth_languages

    drafts = [Draft(1, 0.0, 1.0, "S1", "nl", 0.2, "Hallo")]
    smooth_languages(drafts)
    assert drafts[0].language == "nl"


def test_short_segments_follow_the_file_language() -> None:
    from transcriber.core import Draft, apply_file_language

    drafts = [
        Draft(1, 0.0, 1.0, "S1", "da", 0.98, "Kurz und falsch"),
        Draft(2, 1.0, 6.0, "S2", "en", 0.99, "Länger und anders"),
    ]
    apply_file_language(drafts, "de")
    assert drafts[0].language == "de", "kurzer Abschnitt muss der Dateisprache folgen"
    assert drafts[1].language == "en", "langer Abschnitt behält seine Sprache"


def test_file_language_is_ignored_when_unknown() -> None:
    from transcriber.core import Draft, apply_file_language

    drafts = [Draft(1, 0.0, 1.0, "S1", "da", 0.9, "Kurz")]
    apply_file_language(drafts, None)
    assert drafts[0].language == "da"
