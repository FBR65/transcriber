"""S8, S9, S10, S28: Kommandozeile."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from transcriber import Registry, RunConfig, run_file
from transcriber.cli import app

from .conftest import register_fake_adapters, write_wav

runner = CliRunner()

CONFIG = """
[adapters]
asr = "fake"
diarizer = "fake"
language_id = "fake"
translator = "fake"
voiceprint = ""

[targets]
languages = ["fr"]
"""


def write_config(tmp_path: Path, text: str = CONFIG) -> Path:
    path = tmp_path / "transcriber.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_api_cli_parity(tmp_path: Path, audio_file: Path) -> None:
    config_path = write_config(tmp_path)
    out_dir = tmp_path / "cli-out"
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(audio_file),
            "--config",
            str(config_path),
            "--out",
            str(out_dir),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output

    cli_data = json.loads((out_dir / "probe.json").read_text(encoding="utf-8"))

    registry = Registry()
    register_fake_adapters(registry)
    api = run_file(
        audio_file,
        config=RunConfig(
            asr="fake",
            diarizer="fake",
            language_id="fake",
            translator="fake",
            target_languages=["fr"],
        ),
        registry=registry,
    )

    assert cli_data.pop("created_at") is not None
    api_data = api.to_dict()
    assert api_data.pop("created_at") is not None
    assert cli_data == api_data


def test_corrupt_audio(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_text("das ist kein Ton", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(broken),
            "--config",
            str(write_config(tmp_path)),
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 1
    assert not (out_dir / "broken.json").exists()
    assert "broken.wav" in result.output


def test_silent_audio(tmp_path: Path) -> None:
    silent = write_wav(tmp_path / "still.wav", seconds=2.0, amplitude=0.0)
    config = (
        CONFIG.replace('asr = "fake"', 'asr = "empty"').replace(
            'diarizer = "fake"', 'diarizer = "one"'
        )
    )
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(silent),
            "--config",
            str(write_config(tmp_path, config)),
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((out_dir / "still.json").read_text(encoding="utf-8"))
    assert data["segments"] == []
    assert data["warnings"]


def test_cli_language_switch(tmp_path: Path, audio_file: Path) -> None:
    config_path = write_config(
        tmp_path,
        """
[adapters]
asr = "does-not-exist"
diarizer = "fake"
language_id = "fake"
translator = "fake"
""",
    )
    german = runner.invoke(app, ["transcribe", str(audio_file), "--config", str(config_path)])
    english = runner.invoke(
        app, ["transcribe", str(audio_file), "--config", str(config_path), "--lang", "en"]
    )
    assert german.exit_code == 1
    assert english.exit_code == 1
    assert "nicht registriert" in german.output
    assert "is not registered" in english.output
    assert "does-not-exist" in german.output and "does-not-exist" in english.output
