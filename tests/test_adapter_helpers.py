"""Hilfsfunktionen der Adapter: Token, Shim, Ton einlesen."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from transcriber.adapters.audio_io import load_mono_16k, slice_seconds
from transcriber.adapters.builtin import _hf_token, _token_shim
from transcriber.adapters.mapping import madlad_languages

from .conftest import write_wav


def test_token_from_argument() -> None:
    assert _hf_token("abc") == "abc"


def test_token_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HF_TOKEN", " aus-umgebung ")
    assert _hf_token(None) == "aus-umgebung"


def test_token_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    home = tmp_path / "home"
    (home / ".cache" / "huggingface").mkdir(parents=True)
    (home / ".cache" / "huggingface" / "token").write_text("datei-token\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    assert _hf_token(None) == "datei-token"


def test_token_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _hf_token(None) is None


def test_token_shim_rewrites_argument() -> None:
    seen: dict[str, object] = {}

    def original(*args: object, token: str | None = None, **kwargs: object) -> str:
        seen["token"] = token
        return "ok"

    shim = _token_shim(original, accepts_use_auth_token=False)
    assert shim("repo", "file", use_auth_token="geheim") == "ok"
    assert seen["token"] == "geheim"


def test_token_shim_keeps_existing_token() -> None:
    seen: dict[str, object] = {}

    def original(*args: object, token: str | None = None, **kwargs: object) -> str:
        seen["token"] = token
        return "ok"

    shim = _token_shim(original, accepts_use_auth_token=False)
    shim("repo", "file", token="schon-da", use_auth_token="alt")
    assert seen["token"] == "schon-da"


def test_token_shim_is_noop_when_supported() -> None:
    def original(*args: object, token: str | None = None, **kwargs: object) -> str:
        return "ok"

    assert _token_shim(original, accepts_use_auth_token=True) is original


def test_load_mono_16k_reads_and_downmixes(tmp_path: Path) -> None:
    stereo = write_wav(tmp_path / "stereo.wav", seconds=1.0, rate=44100, channels=2)
    samples = load_mono_16k(stereo)
    assert samples.ndim == 1
    assert samples.dtype == np.float32
    assert abs(len(samples) - 16000) < 400


def test_load_mono_16k_rejects_file_without_audio(tmp_path: Path) -> None:
    path = tmp_path / "leer.txt"
    path.write_text("kein Ton", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_mono_16k(path)
    assert "audio" in str(error.value).lower()


def test_slice_seconds_clamps() -> None:
    samples = np.arange(16000, dtype=np.float32)
    assert slice_seconds(samples, 0.0, 0.5).shape == (8000,)
    assert slice_seconds(samples, 0.9, 5.0).shape == (1600,)
    # Ganz außerhalb der Datei: leerer Ausschnitt, kein Fehler.
    assert slice_seconds(samples, 5.0, 6.0).size == 0
    assert slice_seconds(samples, -1.0, 0.1).shape == (1600,)


def test_madlad_languages_contains_major_codes() -> None:
    assert {"de", "en", "fr", "es", "zh"} <= madlad_languages()


def test_allow_torch_version_global_registers_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    from transcriber.adapters import builtin

    recorded: list[object] = []
    fake_torch = types.SimpleNamespace(
        serialization=types.SimpleNamespace(add_safe_globals=recorded.extend),
        torch_version=types.SimpleNamespace(TorchVersion=object),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)  # type: ignore[arg-type]
    builtin._allow_torch_version_global()
    assert recorded, "keine Klassen freigegeben"
