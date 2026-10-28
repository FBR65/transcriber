"""S27, S30: Sprachkataloge und zweisprachige Doku."""

from __future__ import annotations

import re
from pathlib import Path

from transcriber.i18n import LANGUAGES, catalog, translate

ROOT = Path(__file__).resolve().parents[1]


def placeholders(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"\{([a-z_]+)\}", text)}


def test_i18n_keys_complete() -> None:
    german = catalog("de")
    english = catalog("en")
    assert set(german) == set(english)
    for lang in LANGUAGES:
        for key, text in catalog(lang).items():
            assert text.strip(), f"leerer Text für {key} in {lang}"
    for key, german_text in german.items():
        assert placeholders(german_text) == placeholders(english[key]), (
            f"Platzhalter weichen ab: {key}"
        )


def test_i18n_placeholders_are_filled() -> None:
    """Jeder Platzhalter im Katalog ist im Aufruf vorhanden — hier exemplarisch für alle Keys."""
    for key, text in catalog("de").items():
        params = {name: "x" for name in placeholders(text)}
        assert "{" not in translate(key, "de", **params)


def headings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group(0).strip() for match in re.finditer(r"^#{1,6} .+$", text, re.M)]


def test_docs_bilingual_parity() -> None:
    english = ROOT / "README.md"
    german = ROOT / "README.de.md"
    assert english.is_file(), "README.md fehlt"
    assert german.is_file(), "README.de.md fehlt"
    assert len(headings(english)) > 3
    assert len(headings(english)) == len(headings(german))
