"""S15: Ordner rekursiv, Fehler je Datei, kein Abbruch (SPEC D14 = b)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from transcriber.cli import app

from .conftest import write_wav
from .test_cli import write_config

runner = CliRunner()


def test_folder_partial_failure(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    write_wav(source / "a.wav")
    write_wav(source / "b.wav", seconds=1.0)
    (source / "c.wav").write_text("kein Ton", encoding="utf-8")

    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(source),
            "--config",
            str(write_config(tmp_path)),
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 1, result.output
    assert (out_dir / "a.json").is_file()
    assert (out_dir / "b.json").is_file()
    assert not (out_dir / "c.json").exists()
    assert "c.wav" in result.output
