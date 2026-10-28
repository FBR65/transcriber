"""Randfälle: Fehlerpfade, die die SPEC verlangt. Keine Deko-Tests."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from transcriber import (
    AudioDecodeError,
    Registry,
    RunConfig,
    Segment,
    Source,
    SpeakerInfo,
    Transcript,
    UnknownAdapterError,
    UnsupportedLanguageError,
    export,
)
from transcriber.cli import app
from transcriber.config import Settings, load_settings
from transcriber.errors import TranscriberError
from transcriber.i18n import catalog, normalize_language, translate
from transcriber.licensing import for_adapter

from .conftest import write_wav
from .test_cli import write_config

runner = CliRunner()


def minimal_segment(**overrides: object) -> Segment:
    base: dict[str, object] = {
        "id": "seg-0001",
        "start_s": 0.0,
        "end_s": 1.0,
        "speaker": "S1",
        "language": "de",
        "language_confidence": 0.9,
        "text": "Hallo",
        "translations": {"de": "Hallo"},
    }
    base.update(overrides)
    return Segment(**base)  # type: ignore[arg-type]


def minimal_transcript(**overrides: object) -> Transcript:
    base: dict[str, object] = {
        "created_at": datetime.now(UTC).replace(microsecond=0),
        "source": Source(sha256="0" * 64, duration_s=1.0, sample_rate_hz=16000, channels=1),
        "config": RunConfig(
            asr="a", diarizer="b", language_id="c", translator="d", target_languages=["de"]
        ),
        "speakers": [SpeakerInfo(id="S1", speech_s=1.0, segment_count=1)],
        "segments": [minimal_segment()],
    }
    base.update(overrides)
    return Transcript(**base)  # type: ignore[arg-type]


# --- Ton -------------------------------------------------------------------


def test_probe_missing_file(tmp_path: Path) -> None:
    from transcriber.audio import probe

    with pytest.raises(AudioDecodeError) as error:
        probe(tmp_path / "gibtsnicht.wav")
    assert error.value.params()["detail"] == "file not found"


def test_probe_rejects_video_without_audio(tmp_path: Path) -> None:
    from transcriber.audio import probe

    video = tmp_path / "stumm.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
            "-i", "color=c=black:s=64x64:d=0.4",
            "-an", str(video),
        ],
        check=True,
    )
    with pytest.raises(AudioDecodeError) as error:
        probe(video)
    assert "no audio stream" in error.value.params()["detail"]


def test_probe_reads_real_values(audio_file: Path) -> None:
    from transcriber.audio import probe

    source = probe(audio_file)
    assert source.sample_rate_hz == 16000
    assert source.channels == 1
    assert source.duration_s == pytest.approx(2.0, abs=0.05)
    assert len(source.sha256) == 64


# --- Datenmodell -----------------------------------------------------------


def test_segment_rejects_inverted_times() -> None:
    with pytest.raises(ValidationError):
        minimal_segment(start_s=2.0, end_s=1.0)


def test_transcript_rejects_overlap() -> None:
    with pytest.raises(ValidationError):
        minimal_transcript(
            segments=[
                minimal_segment(id="a", start_s=0.0, end_s=1.0),
                minimal_segment(id="b", start_s=0.5, end_s=1.5),
            ]
        )


def test_transcript_rejects_unknown_speaker() -> None:
    with pytest.raises(ValidationError):
        minimal_transcript(segments=[minimal_segment(speaker="S9")])


def test_run_config_needs_a_target_language() -> None:
    with pytest.raises(ValidationError):
        RunConfig(asr="a", diarizer="b", language_id="c", translator="d", target_languages=[])


# --- Registry --------------------------------------------------------------


class FakeEntryPoint:
    name = "test-plugin"

    def load(self) -> object:
        def register(registry: Registry) -> None:
            registry.register("asr", "from-plugin", lambda: object())

        return register


def test_registry_discover_registers_plugin() -> None:
    registry = Registry()
    registry.discover(plugins=[FakeEntryPoint()])
    assert registry.has("asr", "from-plugin")
    assert registry.ports() == ["asr"]
    assert registry.names("asr") == ["from-plugin"]


def test_registry_discover_rejects_non_callable() -> None:
    class Broken:
        name = "broken"

        def load(self) -> object:
            return 42

    registry = Registry()
    with pytest.raises(TypeError):
        registry.discover(plugins=[Broken()])


def test_registry_rejects_empty_name() -> None:
    registry = Registry()
    with pytest.raises(ValueError):
        registry.register("asr", "", lambda: object())


def test_registry_unknown_adapter_lists_nothing() -> None:
    registry = Registry()
    with pytest.raises(UnknownAdapterError) as error:
        registry.create("asr", "gibt-es-nicht")
    assert "gibt-es-nicht" not in error.value.available
    assert error.value.port == "asr"


# --- Meldungen -------------------------------------------------------------


def test_normalize_language() -> None:
    assert normalize_language("en") == "en"
    assert normalize_language("en-US") == "en"
    assert normalize_language("de_AT") == "de"
    assert normalize_language("zz") == "de"
    assert normalize_language(None) == "de"


def test_unknown_language_falls_back_to_german() -> None:
    """SPEC 3.2: Standard ist Deutsch. Eine unbekannte Sprache fällt still darauf zurück."""
    assert translate("cli.no_adapters", "zz") == catalog("de")["cli.no_adapters"]


def test_missing_placeholder_raises() -> None:
    with pytest.raises(KeyError):
        translate("cli.done", "de")


def test_errors_are_localized() -> None:
    error = UnsupportedLanguageError("xx", ["de", "en"])
    assert error.exit_code == 2
    assert "xx" in error.localized("de")
    assert "nicht unterstützt" in error.localized("de")
    assert "not supported" in error.localized("en")
    generic = TranscriberError("kaputt")
    assert generic.exit_code == 1
    assert generic.params() == {}


# --- Export und Konfiguration ---------------------------------------------


def test_export_rejects_unknown_format(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        export(minimal_transcript(), tmp_path, formats=("docx",))


def test_export_without_source_path(tmp_path: Path) -> None:
    written = export(minimal_transcript(), tmp_path, formats=("txt",))
    assert written[0].name == "transcript.txt"


def test_load_settings_from_file(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    settings = load_settings(config_path, lang="en")
    assert settings.run.asr == "fake"
    assert settings.run.voiceprint is None
    assert settings.run.target_languages == ["fr"]
    assert settings.lang == "en"


def test_settings_defaults_without_file() -> None:
    settings = Settings.from_dict({})
    assert settings.run.asr == "faster-whisper"
    assert settings.run.target_languages == ["de"]


def test_licensing_lookup() -> None:
    assert for_adapter("gibtsnicht") == ()
    entry = for_adapter("madlad")[0]
    assert entry.commercial
    assert not entry.is_blocked()


# --- Kommandozeile ---------------------------------------------------------


def test_cli_without_arguments() -> None:
    result = runner.invoke(app, ["transcribe"])
    assert result.exit_code == 2
    assert "Keine Eingabedatei" in result.output


def test_cli_missing_path(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["transcribe", str(tmp_path / "fehlt.wav"), "--config", str(write_config(tmp_path))]
    )
    assert result.exit_code != 0
    assert "fehlt.wav" in result.output


def test_cli_unknown_format(tmp_path: Path, audio_file: Path) -> None:
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(audio_file),
            "--config",
            str(write_config(tmp_path)),
            "--format",
            "docx",
        ],
    )
    assert result.exit_code == 2
    assert "docx" in result.output


def test_cli_broken_config(tmp_path: Path, audio_file: Path) -> None:
    broken = tmp_path / "kaputt.toml"
    broken.write_text("[adapters\nasr = 1", encoding="utf-8")
    result = runner.invoke(app, ["transcribe", str(audio_file), "--config", str(broken)])
    assert result.exit_code == 1


def test_cli_adapters_and_licenses() -> None:
    adapters_result = runner.invoke(app, ["adapters"])
    assert adapters_result.exit_code == 0
    assert "asr" in adapters_result.output

    licenses_result = runner.invoke(app, ["licenses"])
    assert licenses_result.exit_code == 0
    assert "MIT" in licenses_result.output
    assert "CC-BY-NC" not in licenses_result.output


def test_cli_audio_file_with_other_extension(tmp_path: Path) -> None:
    wav = write_wav(tmp_path / "ohne_endung")
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(wav),
            "--config",
            str(write_config(tmp_path)),
            "--out",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
