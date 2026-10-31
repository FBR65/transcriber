"""Laufzeit-Einstellungen aus TOML."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .models import RunConfig

DEFAULT_ADAPTERS: dict[str, str] = {
    "asr": "faster-whisper",
    "diarizer": "pyannote",
    "language_id": "voxlingua",
    "translator": "madlad",
    "voiceprint": "wespeaker",
}


@dataclass(frozen=True, slots=True)
class Settings:
    run: RunConfig
    lang: str = "de"

    @classmethod
    def from_dict(cls, data: dict[str, object], lang: str | None = None) -> Settings:
        adapters = dict(DEFAULT_ADAPTERS)
        raw_adapters = data.get("adapters", {})
        if isinstance(raw_adapters, dict):
            for key, value in raw_adapters.items():
                adapters[str(key)] = str(value)
        raw_targets = data.get("targets", {})
        languages: list[str] = []
        if isinstance(raw_targets, dict):
            raw_list = raw_targets.get("languages", [])
            if isinstance(raw_list, list):
                languages = [str(item) for item in raw_list]
        if not languages:
            languages = ["de"]
        raw_gallery = data.get("gallery", {})
        gallery: str | None = None
        if isinstance(raw_gallery, dict) and raw_gallery.get("path"):
            gallery = str(raw_gallery["path"])
        run = RunConfig(
            asr=adapters.get("asr", DEFAULT_ADAPTERS["asr"]),
            diarizer=adapters.get("diarizer", DEFAULT_ADAPTERS["diarizer"]),
            language_id=adapters.get("language_id", DEFAULT_ADAPTERS["language_id"]),
            translator=adapters.get("translator", DEFAULT_ADAPTERS["translator"]),
            voiceprint=adapters.get("voiceprint", DEFAULT_ADAPTERS["voiceprint"]) or None,
            gallery=gallery,
            target_languages=languages,
        )
        return cls(run=run, lang=lang or "de")


def load_settings(path: Path | None = None, lang: str | None = None) -> Settings:
    """Liest die Konfiguration. Ohne Pfad gelten die Standardadapter."""
    if path is None:
        return Settings.from_dict({}, lang=lang)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return Settings.from_dict(data, lang=lang)
