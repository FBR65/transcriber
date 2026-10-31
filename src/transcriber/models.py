"""Datenmodell nach SPEC Abschnitt 4."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str | None = None
    sha256: str
    duration_s: float = Field(ge=0)
    sample_rate_hz: int = Field(gt=0)
    channels: int = Field(ge=1)


class SpeakerInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str | None = None
    voiceprint_match: float | None = Field(default=None, ge=0, le=1)
    speech_s: float = Field(ge=0)
    segment_count: int = Field(ge=0)


class Segment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    start_s: float = Field(ge=0)
    end_s: float
    speaker: str
    language: str
    language_confidence: float = Field(ge=0, le=1)
    text: str
    translations: dict[str, str]
    translated_from: str | None = None
    is_final: bool = True

    @model_validator(mode="after")
    def _check(self) -> Segment:
        if self.end_s <= self.start_s:
            raise ValueError("end_s must be greater than start_s")
        return self


class RunConfig(BaseModel):
    """Welche Adapter laufen und in welche Sprachen übersetzt wird."""

    model_config = ConfigDict(frozen=True)

    asr: str
    diarizer: str
    language_id: str
    translator: str
    voiceprint: str | None = None
    gallery: str | None = None
    target_languages: list[str] = Field(min_length=1)


class Transcript(BaseModel):
    """Ergebnis eines Laufs."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["file", "stream"] = "file"
    created_at: datetime
    source: Source
    config: RunConfig
    speakers: list[SpeakerInfo] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Transcript:
        previous_end = -1.0
        for segment in self.segments:
            if segment.start_s < previous_end:
                raise ValueError("segments overlap or are not sorted")
            previous_end = segment.end_s
        known = {speaker.id for speaker in self.speakers}
        for segment in self.segments:
            if segment.speaker not in known:
                raise ValueError(f"segment refers to unknown speaker {segment.speaker!r}")
        return self

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")
