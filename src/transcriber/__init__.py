"""Transcriber — Transkription mit Sprechertrennung, Sprach-ID und Übersetzung."""

from __future__ import annotations

from .config import DEFAULT_ADAPTERS, Settings, load_settings
from .core import run_file
from .errors import (
    AudioDecodeError,
    GalleryConsentError,
    PersonNotFoundError,
    TranscriberError,
    UnknownAdapterError,
    UnsupportedLanguageError,
)
from .exporters import EXPORTERS, export
from .gallery import Gallery, default_gallery_path
from .models import RunConfig, Segment, Source, SpeakerInfo, Transcript
from .ports import (
    AsrEngine,
    AsrSegment,
    Diarizer,
    Exporter,
    LanguageId,
    PersonInfo,
    SpeakerTurn,
    Translator,
    Voiceprint,
    VoiceprintMatch,
)
from .registry import DEFAULT_REGISTRY, Registry

__all__ = [
    "AsrEngine",
    "AsrSegment",
    "AudioDecodeError",
    "DEFAULT_ADAPTERS",
    "DEFAULT_REGISTRY",
    "Diarizer",
    "EXPORTERS",
    "Exporter",
    "Gallery",
    "GalleryConsentError",
    "LanguageId",
    "PersonInfo",
    "PersonNotFoundError",
    "Registry",
    "RunConfig",
    "Segment",
    "Settings",
    "Source",
    "SpeakerInfo",
    "SpeakerTurn",
    "TranscriberError",
    "Transcript",
    "Translator",
    "UnknownAdapterError",
    "UnsupportedLanguageError",
    "Voiceprint",
    "VoiceprintMatch",
    "default_gallery_path",
    "export",
    "load_settings",
    "run_file",
]
__version__ = "0.1.0"
