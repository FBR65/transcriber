"""Schnittstellen (Ports). Der Kern kennt nur diese Protokolle, keinen ML-Code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import Transcript


@dataclass(frozen=True, slots=True)
class AsrSegment:
    start_s: float
    end_s: float
    text: str
    language: str | None = None


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    start_s: float
    end_s: float
    speaker: str


@dataclass(frozen=True, slots=True)
class VoiceprintMatch:
    person_id: str
    name: str
    similarity: float


@dataclass(frozen=True, slots=True)
class PersonInfo:
    person_id: str
    name: str
    created_at: str
    samples: int


@runtime_checkable
class AsrEngine(Protocol):
    def transcribe(
        self, path: Path, options: Mapping[str, Any] | None = None
    ) -> Sequence[AsrSegment]: ...


@runtime_checkable
class Diarizer(Protocol):
    def diarize(
        self, path: Path, options: Mapping[str, Any] | None = None
    ) -> Sequence[SpeakerTurn]: ...


@runtime_checkable
class LanguageId(Protocol):
    def detect(self, path: Path, start_s: float, end_s: float) -> tuple[str, float]: ...


@runtime_checkable
class Translator(Protocol):
    def languages(self) -> set[str]: ...

    def translate(
        self, texts: Sequence[str], source_lang: str, target_lang: str
    ) -> Sequence[str]: ...


@runtime_checkable
class Exporter(Protocol):
    name: str

    def write(self, transcript: Transcript, path: Path) -> None: ...


@runtime_checkable
class Voiceprint(Protocol):
    """Stimmabdruck-Galerie (SPEC Abschnitt 7). Anmeldung nur mit Zustimmung."""

    def identify(self, path: Path, start_s: float, end_s: float) -> VoiceprintMatch | None: ...

    def enroll(
        self, path: Path, start_s: float, end_s: float, name: str, *, consent: bool
    ) -> PersonInfo: ...

    def delete(self, reference: str) -> int: ...

    def people(self) -> list[PersonInfo]: ...


@runtime_checkable
class VideoRenderer(Protocol):
    """Brennt Untertitel in ein Video ein (SPEC D12 = b, S20)."""

    def render(
        self, video: Path, transcript: Transcript, out: Path, language: str | None = None
    ) -> Path: ...
