"""Randfälle der Galerie und der Galerie-Befehle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from transcriber.cli import app
from transcriber.core import speaker_windows
from transcriber.errors import GalleryConsentError
from transcriber.gallery import Gallery, cosine_similarity, default_gallery_path

from .conftest import write_wav

runner = CliRunner()


def test_default_path_lives_under_home() -> None:
    path = default_gallery_path()
    assert path.name == "gallery.db"
    assert path.is_absolute()


def test_cosine_with_zero_vector() -> None:
    zeros = np.zeros(4, dtype=np.float32)
    assert cosine_similarity(zeros, np.ones(4, dtype=np.float32)) == 0.0


def test_match_skips_foreign_dimension(tmp_path: Path) -> None:
    gallery = Gallery(tmp_path / "g.db", threshold=0.5)
    gallery.add("Herr X", np.ones(8, dtype=np.float32), consent=True)
    assert gallery.match(np.ones(4, dtype=np.float32)) is None


def test_empty_embedding_is_rejected(tmp_path: Path) -> None:
    gallery = Gallery(tmp_path / "g.db")
    with pytest.raises(ValueError):
        gallery.add("Herr X", np.zeros(0, dtype=np.float32), consent=True)


def test_blank_reference_is_rejected(tmp_path: Path) -> None:
    gallery = Gallery(tmp_path / "g.db")
    with pytest.raises(ValueError):
        gallery.delete("   ")


def test_speaker_windows_skips_short_turns() -> None:
    windows = speaker_windows(
        [(0.0, 0.2, "S1"), (1.0, 4.0, "S1"), (4.0, 5.0, "S2")], limit=2
    )
    assert windows["S1"] == [(1.0, 4.0)]
    assert windows["S2"] == [(4.0, 5.0)]


def test_cli_enroll_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["gallery", "enroll", str(tmp_path / "fehlt.wav"), "--name", "Herr X", "--consent",
         "--adapter", "fake", "--gallery", str(tmp_path / "g.db")],
    )
    assert result.exit_code == 1
    assert "fehlt.wav" in result.output


def test_cli_enroll_reports_adapter_error(tmp_path: Path) -> None:
    from transcriber import DEFAULT_REGISTRY

    class Refusing:
        def __init__(self, gallery: str | None = None) -> None:
            self.gallery = gallery

        def enroll(self, *args: object, **kwargs: object) -> object:
            raise GalleryConsentError("Herr X")

        def people(self) -> list[object]:
            return []

        def delete(self, reference: str) -> int:
            return 0

    DEFAULT_REGISTRY.register("voiceprint", "refusing", Refusing)
    audio = write_wav(tmp_path / "stimme.wav")
    result = runner.invoke(
        app,
        ["gallery", "enroll", str(audio), "--name", "Herr X", "--consent",
         "--adapter", "refusing", "--gallery", str(tmp_path / "g.db")],
    )
    assert result.exit_code == 2
    assert "Ohne Zustimmung" in result.output
