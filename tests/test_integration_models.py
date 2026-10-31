"""Echter Lauf mit echten Modellen. Nur mit `-m integration` und nach tools/fetch_samples.py.

Diese Tests prüfen die Verdrahtung, nicht die Qualität. Sie sind langsam und brauchen Netz
beim ersten Mal. Geprüft wird: Text erkannt, Sprache erkannt, übersetzt, Sprecher geliefert.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from transcriber import (
    AsrSegment,
    Registry,
    RunConfig,
    SpeakerTurn,
    run_file,
)
from transcriber.adapters.builtin import (
    MadladTranslator,
    PyannoteDiarizer,
    VoxLinguaLanguageId,
    WhisperAsr,
)

pytestmark = pytest.mark.integration

SAMPLE = Path.home() / ".cache" / "transcriber" / "samples" / "jfk.wav"


@pytest.fixture(scope="module")
def sample() -> Path:
    if not SAMPLE.is_file():
        pytest.skip(f"Testsample fehlt: {SAMPLE} (tools/fetch_samples.py)")
    return SAMPLE


def test_whisper_transcribes_english(sample: Path) -> None:
    asr = WhisperAsr()
    try:
        started = time.perf_counter()
        segments = asr.transcribe(sample)
        elapsed = time.perf_counter() - started
    finally:
        asr.release()
    assert segments, "kein Text erkannt"
    text = " ".join(segment.text for segment in segments).lower()
    assert "country" in text or "fellow" in text, text[:200]
    assert elapsed < 120, f"zu langsam: {elapsed:.1f}s"
    print(f"Whisper: {len(segments)} Segmente in {elapsed:.1f}s")


def test_language_id_finds_english(sample: Path) -> None:
    language_id = VoxLinguaLanguageId()
    try:
        language, confidence = language_id.detect(sample, 0.5, 3.5)
    finally:
        language_id.release()
    assert language == "en", (language, confidence)
    print(f"Sprach-ID: {language} mit {confidence:.2f}")


def test_madlad_translates_to_german() -> None:
    translator = MadladTranslator()
    try:
        result = translator.translate(
            ["And so my fellow Americans, ask not what your country can do for you."],
            "en",
            "de",
        )
    finally:
        translator.release()
    assert len(result) == 1
    assert result[0].strip()
    original = "and so my fellow americans, ask not what your country can do for you"
    assert result[0].lower().strip(" .") != original
    print(f"MADLAD: {result[0]}")


def test_pyannote_returns_speakers(sample: Path) -> None:
    diarizer = PyannoteDiarizer()
    try:
        turns = diarizer.diarize(sample)
    finally:
        diarizer.release()
    assert turns, "keine Sprecherwechsel"
    labels = {turn.speaker for turn in turns}
    assert len(labels) >= 1
    assert all(turn.end_s > turn.start_s for turn in turns)
    print(f"pyannote: {len(turns)} Abschnitte, Sprecher {sorted(labels)}")


def test_full_run_with_real_models(sample: Path) -> None:
    registry = Registry()
    registry.discover()
    config = RunConfig(
        asr="faster-whisper",
        diarizer="pyannote",
        language_id="voxlingua",
        translator="madlad",
        target_languages=["de"],
    )
    started = time.perf_counter()
    transcript = run_file(sample, config=config, registry=registry)
    elapsed = time.perf_counter() - started

    assert transcript.segments, "leeres Transkript"
    assert transcript.speakers, "keine Sprecher"
    for segment in transcript.segments:
        assert segment.translations["de"].strip()
    assert all(s.id.startswith("S") for s in transcript.speakers)
    print(
        f"Gesamtlauf: {len(transcript.segments)} Segmente, "
        f"{len(transcript.speakers)} Sprecher, {elapsed:.1f}s"
    )


class _FixedAsr:
    def transcribe(self, path: Path, options: object | None = None) -> list[AsrSegment]:
        return [AsrSegment(0.0, 1.0, "Hallo Welt", "de")]

    def release(self) -> None:
        return None


class _FixedDiarizer:
    def diarize(self, path: Path, options: object | None = None) -> list[SpeakerTurn]:
        return [SpeakerTurn(0.0, 1.0, "S1")]

    def release(self) -> None:
        return None


def test_voiceprint_gallery_roundtrip(sample: Path, tmp_path: Path) -> None:
    """S16, S18 mit echtem Stimmabdruck-Modell und echter Galerie."""
    import shutil
    import subprocess

    from transcriber.adapters.voiceprint import WeSpeakerVoiceprint

    voiceprint = WeSpeakerVoiceprint(gallery=tmp_path / "gallery.db", threshold=0.5)
    try:
        person = voiceprint.enroll(sample, 0.5, 6.0, "JFK", consent=True)
        assert person.samples == 1

        same = voiceprint.identify(sample, 0.5, 5.0)
        assert same is not None
        assert same.name == "JFK"

        # Fremde Stimme: derselbe Ton, deutlich verändert. Die Ähnlichkeit muss sinken.
        shifted = tmp_path / "verschoben.wav"
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-i", str(sample),
                "-af", "asetrate=16000*1.5,aresample=16000,atempo=0.667",
                str(shifted),
            ],
            check=True,
        )
        other = voiceprint.identify(shifted, 0.5, 5.0)
        other_similarity = other.similarity if other is not None else 0.0
        assert other_similarity < same.similarity, (
            f"veränderte Stimme zu ähnlich: {other_similarity:.2f} gegen {same.similarity:.2f}"
        )

        assert voiceprint.delete("JFK") == 1
        assert voiceprint.identify(sample, 0.5, 5.0) is None
        assert voiceprint.people() == []
    finally:
        voiceprint.release()
