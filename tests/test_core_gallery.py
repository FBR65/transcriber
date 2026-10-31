"""S16, S17: Galerie im Kern. Mit Test-Adaptern, ohne Modelle."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from transcriber import (
    PersonInfo,
    Registry,
    RunConfig,
    VoiceprintMatch,
    run_file,
)

from .conftest import register_fake_adapters, write_wav

KNOWN = np.array([1.0, 0.0, 0.0], dtype=np.float32)
UNKNOWN = np.array([0.0, 1.0, 0.0], dtype=np.float32)


class FakeVoiceprint:
    """Erkennt den Sprecher mit dem Ton bei Sekunde 0, alles andere ist fremd."""

    def __init__(self, people: list[PersonInfo] | None = None, gallery: str | None = None) -> None:
        self._people = people if people is not None else []
        self.gallery = gallery

    def people(self) -> list[PersonInfo]:
        return list(self._people)

    def identify(self, path: Path, start_s: float, end_s: float) -> VoiceprintMatch | None:
        if start_s < 0.5 and self._people:
            return VoiceprintMatch(
                person_id=self._people[0].person_id, name=self._people[0].name, similarity=0.93
            )
        return None

    def enroll(
        self, path: Path, start_s: float, end_s: float, name: str, *, consent: bool
    ) -> PersonInfo:
        raise NotImplementedError

    def delete(self, reference: str) -> int:
        raise NotImplementedError


def build(people: list[PersonInfo]) -> Registry:
    registry = Registry()
    register_fake_adapters(registry)
    registry.register("voiceprint", "fake", lambda gallery=None: FakeVoiceprint(people, gallery))
    return registry


def config() -> RunConfig:
    return RunConfig(
        asr="fake",
        diarizer="fake",
        language_id="fake",
        translator="fake",
        voiceprint="fake",
        target_languages=["de"],
    )


def test_gallery_recognises_known_speaker(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ton.wav")
    people = [PersonInfo(person_id="p1", name="Herr X", created_at="2026-10-28", samples=1)]
    single = config().model_copy(update={"diarizer": "one"})
    transcript = run_file(audio, config=single, registry=build(people))

    names = {speaker.id: speaker.name for speaker in transcript.speakers}
    assert names["S1"] == "Herr X"
    matches = {speaker.id: speaker.voiceprint_match for speaker in transcript.speakers}
    assert matches["S1"] == 0.93
    assert transcript.warnings == []


def test_gallery_unknown_speaker_stays_unnamed(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ton.wav")
    people = [PersonInfo(person_id="p1", name="Herr X", created_at="2026-10-28", samples=1)]
    transcript = run_file(audio, config=config(), registry=build(people))

    names = {speaker.id: speaker.name for speaker in transcript.speakers}
    assert names["S2"] is None, "fremder Sprecher darf keinen Namen bekommen"
    assert transcript.warnings, "fehlender Treffer muss gemeldet werden"
    assert "Galerie" in transcript.warnings[0]


def test_empty_gallery_gives_no_names_and_no_warning(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ton.wav")
    transcript = run_file(audio, config=config(), registry=build([]))

    assert all(speaker.name is None for speaker in transcript.speakers)
    assert transcript.warnings == []


def test_gallery_path_is_handed_to_the_adapter(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "ton.wav")
    seen: dict[str, str | None] = {}

    class Recorder(FakeVoiceprint):
        def __init__(self, gallery: str | None = None) -> None:
            seen["gallery"] = gallery
            super().__init__([], gallery)

    registry = Registry()
    register_fake_adapters(registry)
    registry.register("voiceprint", "rec", Recorder)
    config_with_gallery = config().model_copy(update={"voiceprint": "rec", "gallery": "/tmp/x.db"})
    run_file(audio, config=config_with_gallery, registry=registry)
    assert seen["gallery"] == "/tmp/x.db"
