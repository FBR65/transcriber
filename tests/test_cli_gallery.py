"""Galerie über die Kommandozeile: S18, S19 und die Liste."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from transcriber.cli import app

from .conftest import write_wav

runner = CliRunner()


def gal(tmp_path: Path) -> str:
    return str(tmp_path / "galerie" / "gallery.db")


def test_enroll_refuses_without_consent(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "stimme.wav")
    result = runner.invoke(
        app,
        ["gallery", "enroll", str(audio), "--name", "Herr X", "--adapter", "fake",
         "--gallery", gal(tmp_path)],
    )
    assert result.exit_code == 2
    assert "Ohne Zustimmung" in result.output

    listing = runner.invoke(
        app, ["gallery", "list", "--adapter", "fake", "--gallery", gal(tmp_path)]
    )
    assert "leer" in listing.output


def test_enroll_list_delete(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "stimme.wav")
    path = gal(tmp_path)

    enrolled = runner.invoke(
        app,
        ["gallery", "enroll", str(audio), "--name", "Herr X", "--consent",
         "--adapter", "fake", "--gallery", path],
    )
    assert enrolled.exit_code == 0, enrolled.output
    assert "Herr X" in enrolled.output

    listing = runner.invoke(app, ["gallery", "list", "--adapter", "fake", "--gallery", path])
    assert listing.exit_code == 0
    assert "Herr X" in listing.output
    assert "1" in listing.output

    deleted = runner.invoke(
        app, ["gallery", "delete", "Herr X", "--adapter", "fake", "--gallery", path]
    )
    assert deleted.exit_code == 0, deleted.output
    assert "Gelöscht" in deleted.output

    after = runner.invoke(app, ["gallery", "list", "--adapter", "fake", "--gallery", path])
    assert "leer" in after.output


def test_delete_unknown_person(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["gallery", "delete", "Niemand", "--adapter", "fake", "--gallery", gal(tmp_path)],
    )
    assert result.exit_code == 2
    assert "Niemand" in result.output


def test_english_messages(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["gallery", "delete", "Niemand", "--adapter", "fake", "--gallery", gal(tmp_path),
         "--lang", "en"],
    )
    assert result.exit_code == 2
    assert "No such person" in result.output


def test_transcribe_uses_gallery_names(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "konferenz.wav")
    path = gal(tmp_path)
    enrolled = runner.invoke(
        app,
        ["gallery", "enroll", str(audio), "--name", "Herr X", "--consent", "--start", "0",
         "--end", "1", "--adapter", "fake", "--gallery", path],
    )
    assert enrolled.exit_code == 0, enrolled.output

    config = tmp_path / "c.toml"
    config.write_text(
        '[adapters]\nasr="fake"\ndiarizer="one"\nlanguage_id="fake"\n'
        'translator="fake"\nvoiceprint="fake"\n\n[targets]\nlanguages=["de"]\n',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["transcribe", str(audio), "--config", str(config), "--out", str(out),
         "--gallery", path],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "konferenz.json").read_text(encoding="utf-8"))
    assert data["speakers"][0]["name"] == "Herr X"
    assert data["speakers"][0]["voiceprint_match"] is not None
