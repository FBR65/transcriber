"""Fehlerpfade von ffprobe, Export und Lizenzprüfung.

subprocess ist eine Grenze zur Außenwelt, kein Logik-Mock: der Kern wird echt ausgeführt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from transcriber import AudioDecodeError, Registry
from transcriber import audio as audio_module
from transcriber.cli import app
from transcriber.config import load_settings
from transcriber.exporters import _spoken, _stamp
from transcriber.i18n import catalog
from transcriber.licensing import LicenceEntry

from .test_edges import minimal_segment


def fake_probe(monkeypatch: pytest.MonkeyPatch, payload: str, returncode: int = 0) -> None:
    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode, stdout=payload, stderr="kaputt")

    monkeypatch.setattr(audio_module.subprocess, "run", fake_run)


def existing_file(tmp_path: Path) -> Path:
    probe_file = tmp_path / "datei.wav"
    probe_file.write_bytes(b"RIFF")
    return probe_file


def test_ffprobe_reports_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(monkeypatch, "", returncode=1)
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert "kaputt" in str(error.value.params()["detail"])


def test_ffprobe_rejects_broken_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(monkeypatch, "kein json")
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert error.value.params()["detail"] == "ffprobe output is not JSON"


def test_probe_rejects_unreadable_stream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(monkeypatch, '{"streams": ["kein objekt"]}')
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert error.value.params()["detail"] == "unreadable audio stream"


def test_probe_rejects_bad_sample_rate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(monkeypatch, '{"streams": [{"sample_rate": "viel", "channels": "1"}]}')
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert error.value.params()["detail"] == "invalid sample rate or channel count"


def test_probe_rejects_missing_duration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(
        monkeypatch, '{"streams": [{"sample_rate": "16000", "channels": "1"}], "format": {}}'
    )
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert error.value.params()["detail"] == "invalid duration"


def test_probe_rejects_zero_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(
        monkeypatch,
        '{"streams": [{"sample_rate": "0", "channels": "1", "duration": "1.0"}]}',
    )
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert error.value.params()["detail"] == "invalid audio parameters"


def test_probe_uses_format_duration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)
    fake_probe(
        monkeypatch,
        '{"streams": [{"sample_rate": "16000", "channels": "2"}],'
        ' "format": {"duration": "3.5"}}',
    )
    source = audio_module.probe(path)
    assert source.duration_s == 3.5
    assert source.channels == 2


def test_probe_timeout_is_decoded_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = existing_file(tmp_path)

    def boom(*args: object, **kwargs: object) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr(audio_module.subprocess, "run", boom)
    with pytest.raises(AudioDecodeError) as error:
        audio_module.probe(path)
    assert "ffprobe" in str(error.value.params()["detail"])


# --- Export ----------------------------------------------------------------


def test_spoken_falls_back_to_text() -> None:
    assert _spoken(minimal_segment(translations={})) == "Hallo"
    assert _spoken(minimal_segment(translations={"de": "Hallo"})) == "Hallo"


def test_stamp_rejects_negative() -> None:
    with pytest.raises(ValueError):
        _stamp(-1.0)


# --- Lizenzen --------------------------------------------------------------


def test_blocked_licence_is_detected() -> None:
    assert LicenceEntry("x", "p", "m", "CC-BY-NC-4.0", True).is_blocked()
    assert LicenceEntry("x", "p", "m", "MIT", False).is_blocked()
    assert not LicenceEntry("x", "p", "m", "MIT", True).is_blocked()


# --- Katalog und Konfiguration --------------------------------------------


def test_missing_catalog_raises() -> None:
    with pytest.raises(KeyError):
        catalog("zz")


def test_load_settings_without_path() -> None:
    settings = load_settings(None)
    assert settings.run.asr == "faster-whisper"
    assert settings.lang == "de"


# --- Kommandozeile ---------------------------------------------------------


def test_cli_target_option_wins(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from .conftest import write_wav

    audio = write_wav(tmp_path / "ton.wav")
    config = tmp_path / "c.toml"
    config.write_text(
        '[adapters]\nasr="fake"\ndiarizer="fake"\nlanguage_id="fake"\n'
        'translator="fake"\nvoiceprint=""\n\n[targets]\nlanguages=["fr"]\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "transcribe",
            str(audio),
            "--config",
            str(config),
            "--target",
            "es",
            "--out",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "out" / "ton.json").read_text(encoding="utf-8")
    assert "[translated:es]" in text


def test_cli_adapters_without_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from transcriber import cli as cli_module

    monkeypatch.setattr(cli_module, "DEFAULT_REGISTRY", Registry())
    result = CliRunner().invoke(app, ["adapters"])
    assert result.exit_code == 0
    assert "Keine Adapter" in result.output
