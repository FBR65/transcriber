"""Adapter mit Attrappen an der Modellgrenze. Kein Modell wird geladen."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from transcriber.adapters.builtin import (
    MadladTranslator,
    PyannoteDiarizer,
    VoxLinguaLanguageId,
    WhisperAsr,
)
from transcriber.adapters.mapping import (
    is_supported_target,
    language_code,
    madlad_prompt,
    segments_from_whisper,
    turns_from_annotation,
)
from transcriber.ports import AsrSegment


def test_language_code_rewrites_obsolete_codes() -> None:
    assert language_code("en: English") == "en"
    assert language_code("iw: Hebrew") == "he"
    assert language_code("jw: Javanese") == "jv"
    assert language_code("DE") == "de"


def test_madlad_prompt_needs_a_language() -> None:
    assert madlad_prompt("de", "Hello") == "<2de> Hello"
    with pytest.raises(ValueError):
        madlad_prompt("", "Hello")


def test_supported_targets() -> None:
    assert is_supported_target("de")
    assert is_supported_target("EN")
    assert not is_supported_target("xx")


def test_segments_from_whisper_drops_empty_and_broken() -> None:
    items = [
        SimpleNamespace(start=0.0, end=1.0, text=" Hallo "),
        SimpleNamespace(start=1.0, end=1.0, text="kaputt"),
        SimpleNamespace(start=1.0, end=2.0, text="   "),
        SimpleNamespace(start=2.0, end=3.0, text="Welt"),
    ]
    result = segments_from_whisper(items)
    assert result == [
        AsrSegment(0.0, 1.0, "Hallo", None),
        AsrSegment(2.0, 3.0, "Welt", None),
    ]


def test_turns_from_annotation_sorts_and_filters() -> None:
    result = turns_from_annotation(
        [(2.0, 3.0, "B"), (0.0, 1.0, "A"), (1.0, 1.0, "kaputt")]
    )
    assert [(turn.start_s, turn.speaker) for turn in result] == [(0.0, "A"), (2.0, "B")]


def test_whisper_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.released = False

        def transcribe(self, path: str, **kwargs: object) -> tuple[list[object], object]:
            return [SimpleNamespace(start=0.0, end=1.5, text=" hallo welt ")], SimpleNamespace(
                language="en"
            )

    module.WhisperModel = FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)

    asr = WhisperAsr()
    assert asr.transcribe(Path("x.wav")) == [AsrSegment(0.0, 1.5, "hallo welt", None)]
    asr.release()
    assert asr._model is None


def test_madlad_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    transformers = types.ModuleType("transformers")

    class Encoded(dict):  # type: ignore[type-arg]
        def to(self, device: str) -> Encoded:
            return self

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, name: str) -> FakeTokenizer:
            return cls()

        def __call__(self, prompts: list[str], **kwargs: object) -> Encoded:
            assert all(prompt.startswith("<2de> ") for prompt in prompts)
            return Encoded(input_ids=[[0] * len(prompts)])

        def batch_decode(self, generated: object, **kwargs: object) -> list[str]:
            return [f"übersetzt {index}" for index, _ in enumerate(generated)]

    class FakeModel:
        @classmethod
        def from_pretrained(cls, name: str, **kwargs: object) -> FakeModel:
            return cls()

        def to(self, device: str) -> FakeModel:
            return self

        def eval(self) -> FakeModel:
            return self

        def generate(self, **kwargs: object) -> list[list[int]]:
            return [[1], [2]]

    transformers.AutoTokenizer = FakeTokenizer  # type: ignore[attr-defined]
    transformers.AutoModelForSeq2SeqLM = FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    translator = MadladTranslator(device="cpu")
    assert translator.languages() >= {"de", "en"}
    assert translator.translate(["Hallo", "Welt"], "en", "de") == [
        "übersetzt 0",
        "übersetzt 1",
    ]
    with pytest.raises(ValueError):
        translator.translate(["Hallo"], "en", "xx")
    translator.release()


def test_pyannote_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    pyannote = types.ModuleType("pyannote")
    audio_module = types.ModuleType("pyannote.audio")

    class FakeAnnotation:
        def itertracks(self, yield_label: bool = False) -> list[tuple[object, object, str]]:
            return [
                (SimpleNamespace(start=0.0, end=1.0), None, "SPEAKER_00"),
                (SimpleNamespace(start=1.0, end=2.0), None, "SPEAKER_01"),
            ]

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, model: str, token: str | None = None) -> FakePipeline:
            return cls()

        def to(self, device: object) -> FakePipeline:
            return self

        def __call__(self, path: str) -> object:
            # pyannote 4.x liefert ein Objekt mit speaker_diarization.
            return SimpleNamespace(speaker_diarization=FakeAnnotation())

    audio_module.Pipeline = FakePipeline  # type: ignore[attr-defined]
    pyannote.audio = audio_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyannote", pyannote)
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio_module)

    diarizer = PyannoteDiarizer(device="cpu")
    turns = diarizer.diarize(Path("x.wav"))
    assert [(turn.start_s, turn.speaker) for turn in turns] == [
        (0.0, "SPEAKER_00"),
        (1.0, "SPEAKER_01"),
    ]
    diarizer.release()


def test_voxlingua_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Der Klassifikator ist eine Attrappe, der Ton wird echt gelesen."""
    from .conftest import write_wav

    audio = write_wav(tmp_path / "rede.wav", seconds=2.0, rate=16000)

    speechbrain = types.ModuleType("speechbrain")
    inference = types.ModuleType("speechbrain.inference")
    classifiers = types.ModuleType("speechbrain.inference.classifiers")

    class FakeClassifier:
        @classmethod
        def from_hparams(cls, source: str, run_opts: object, savedir: object) -> FakeClassifier:
            return cls()

        def classify_batch(
            self, waveform: object
        ) -> tuple[object, list[float], object, list[str]]:
            assert waveform.shape[0] == 1
            return None, [-0.2], None, ["iw: Hebrew"]

    classifiers.EncoderClassifier = FakeClassifier  # type: ignore[attr-defined]
    speechbrain.inference = inference  # type: ignore[attr-defined]
    inference.classifiers = classifiers  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "speechbrain", speechbrain)
    monkeypatch.setitem(sys.modules, "speechbrain.inference", inference)
    monkeypatch.setitem(sys.modules, "speechbrain.inference.classifiers", classifiers)

    language_id = VoxLinguaLanguageId(device="cpu")
    language, confidence = language_id.detect(audio, 0.5, 1.0)
    assert language == "he"
    assert 0.0 <= confidence <= 1.0
    language_id.release()


def test_language_id_expands_very_short_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ein 0,04-s-Abschnitt darf die Faltung nicht sprengen."""
    from .conftest import write_wav

    audio = write_wav(tmp_path / "kurz.wav", seconds=2.0, rate=16000)
    speechbrain = types.ModuleType("speechbrain")
    inference = types.ModuleType("speechbrain.inference")
    classifiers = types.ModuleType("speechbrain.inference.classifiers")
    seen: dict[str, int] = {}

    class FakeClassifier:
        @classmethod
        def from_hparams(cls, source: str, run_opts: object, savedir: object) -> FakeClassifier:
            return cls()

        def classify_batch(
            self, waveform: object
        ) -> tuple[object, list[float], object, list[str]]:
            seen["samples"] = int(waveform.shape[1])
            return None, [-0.1], None, ["de: German"]

    classifiers.EncoderClassifier = FakeClassifier  # type: ignore[attr-defined]
    speechbrain.inference = inference  # type: ignore[attr-defined]
    inference.classifiers = classifiers  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "speechbrain", speechbrain)
    monkeypatch.setitem(sys.modules, "speechbrain.inference", inference)
    monkeypatch.setitem(sys.modules, "speechbrain.inference.classifiers", classifiers)

    language_id = VoxLinguaLanguageId(device="cpu")
    language, _confidence = language_id.detect(audio, 1.0, 1.04)
    assert language == "de"
    assert seen["samples"] >= 7000, f"zu kurz: {seen['samples']} Abtastwerte"
