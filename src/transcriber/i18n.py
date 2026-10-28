"""Meldungen in Deutsch und Englisch (SPEC 3.2, D6 = c). Standard ist Deutsch."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CATALOG_DIR = Path(__file__).with_name("i18n")
LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"


@lru_cache(maxsize=8)
def catalog(lang: str) -> dict[str, str]:
    path = CATALOG_DIR / f"{lang}.json"
    if not path.is_file():
        raise KeyError(f"no catalog for language {lang!r}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"catalog {path} is not an object")
    return {str(key): str(value) for key, value in data.items()}


def normalize_language(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    short = lang.split("-")[0].split("_")[0].lower()
    return short if short in LANGUAGES else DEFAULT_LANGUAGE


def translate(key: str, lang: str = DEFAULT_LANGUAGE, **params: object) -> str:
    """Setzt den Text aus dem Katalog ein. Fehlender Schlüssel oder Platzhalter ist ein Fehler."""
    language = normalize_language(lang)
    text = catalog(language)[key]
    try:
        return text.format(**params)
    except KeyError as missing:
        raise KeyError(f"missing placeholder {missing} for key {key!r}") from None
