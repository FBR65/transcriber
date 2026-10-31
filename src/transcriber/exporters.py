"""Export nach json, srt, vtt und txt (SPEC Abschnitt 2 und S7)."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from .models import Segment, Transcript


def _stamp(seconds: float, separator: str = ",") -> str:
    if seconds < 0:
        raise ValueError("negative timestamp")
    milliseconds = int(round(seconds * 1000))
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _spoken(segment: Segment, language: str | None = None) -> str:
    """Untertitel zeigen die Zielsprache, sonst den Originaltext."""
    if language is not None:
        if language in segment.translations:
            return segment.translations[language]
        return segment.text
    if segment.translations:
        first = next(iter(sorted(segment.translations.values())))
        return first
    return segment.text


def write_json(transcript: Transcript, path: Path) -> None:
    payload = transcript.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def write_srt(transcript: Transcript, path: Path, language: str | None = None) -> None:
    lines: list[str] = []
    for index, segment in enumerate(transcript.segments, start=1):
        lines.append(str(index))
        lines.append(f"{_stamp(segment.start_s)} --> {_stamp(segment.end_s)}")
        lines.append(f"[{segment.speaker}] {_spoken(segment, language)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_vtt(transcript: Transcript, path: Path) -> None:
    lines = ["WEBVTT", ""]
    for segment in transcript.segments:
        lines.append(f"{_stamp(segment.start_s, '.')} --> {_stamp(segment.end_s, '.')}")
        lines.append(f"<v {segment.speaker}>{_spoken(segment)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_txt(transcript: Transcript, path: Path) -> None:
    lines: list[str] = []
    for segment in transcript.segments:
        lines.append(f"[{_stamp(segment.start_s, '.')}] [{segment.speaker}] {segment.text}")
        for language, text in sorted(segment.translations.items()):
            if text != segment.text:
                lines.append(f"    {language}: {text}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


EXPORTERS: dict[str, Callable[[Transcript, Path], None]] = {
    "json": write_json,
    "srt": write_srt,
    "vtt": write_vtt,
    "txt": write_txt,
}


def export(
    transcript: Transcript, directory: Path, formats: Sequence[str] = ("json",)
) -> list[Path]:
    """Schreibt je Format eine Datei. Der Name kommt aus der Quelldatei."""
    unknown = [name for name in formats if name not in EXPORTERS]
    if unknown:
        raise ValueError(f"unknown export format: {', '.join(sorted(unknown))}")
    stem = (
        Path(transcript.source.path).stem if transcript.source.path else "transcript"
    )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in formats:
        target = directory / f"{stem}.{name}"
        EXPORTERS[name](transcript, target)
        written.append(target)
    return written
