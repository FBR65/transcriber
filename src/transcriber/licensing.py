"""Lizenzangaben der Standardmodelle. Grundlage für `transcriber licenses` und den Test (D8)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_ADAPTERS

NON_COMMERCIAL_MARKERS = ("-NC", "NC-", "noncommercial", "research-only", "proprietary")


@dataclass(frozen=True, slots=True)
class LicenceEntry:
    adapter: str
    port: str
    model: str
    licence: str
    commercial: bool
    note: str = ""

    def is_blocked(self) -> bool:
        if not self.commercial:
            return True
        lowered = self.licence.lower()
        return any(marker.lower() in lowered for marker in NON_COMMERCIAL_MARKERS)


LICENCES: tuple[LicenceEntry, ...] = (
    LicenceEntry("faster-whisper", "asr", "Systran/faster-whisper-large-v3", "MIT", True),
    LicenceEntry("pyannote", "diarizer", "pyannote/speaker-diarization-3.1", "MIT", True,
                 "gated: Nutzerbedingungen und HF-Token"),
    LicenceEntry("pyannote", "diarizer", "pyannote/segmentation-3.0", "MIT", True, "gated"),
    LicenceEntry("wespeaker", "voiceprint", "pyannote/wespeaker-voxceleb-resnet34-LM",
                 "CC-BY-4.0", True, "Namensnennung im NOTICE"),
    LicenceEntry("voxlingua", "language_id", "speechbrain/lang-id-voxlingua107-ecapa",
                 "Apache-2.0", True, "Trainingsdaten aus YouTube-Mitschnitten"),
    LicenceEntry("madlad", "translator", "google/madlad400-3b-mt", "Apache-2.0", True),
)


def defaults() -> tuple[LicenceEntry, ...]:
    """Je Standardadapter die zugehörigen Einträge."""
    wanted = set(DEFAULT_ADAPTERS.values())
    return tuple(entry for entry in LICENCES if entry.adapter in wanted)


def for_adapter(adapter: str) -> tuple[LicenceEntry, ...]:
    return tuple(entry for entry in LICENCES if entry.adapter == adapter)


def blocked_defaults() -> tuple[LicenceEntry, ...]:
    return tuple(entry for entry in defaults() if entry.is_blocked())
