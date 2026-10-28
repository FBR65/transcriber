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
