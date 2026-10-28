"""Ton einlesen und prüfen. Nutzt ffprobe und die Standardbibliothek, keinen ML-Code."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from .errors import AudioDecodeError
from .models import Source

AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac", ".mp4", ".webm", ".opus"})


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, Any]:
    binary = shutil.which("ffprobe") or "ffprobe"
    command = [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-select_streams",
        "a:0",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:  # pragma: no cover - Umgebung
        raise AudioDecodeError(str(path), f"ffprobe: {error}") from error
    if completed.returncode != 0:
        raise AudioDecodeError(str(path), (completed.stderr or "ffprobe failed").strip()[:200])
    try:
        return cast(dict[str, Any], json.loads(completed.stdout or "{}"))
    except json.JSONDecodeError as error:
        raise AudioDecodeError(str(path), "ffprobe output is not JSON") from error


def probe(path: Path) -> Source:
    """Liest Dauer, Abtastrate und Kanäle. Wirft AudioDecodeError, wenn kein Ton vorliegt."""
    path = Path(path)
    if not path.is_file():
        raise AudioDecodeError(str(path), "file not found")
    data = _ffprobe(path)
    streams = data.get("streams") or []
    if not isinstance(streams, list) or not streams:
        raise AudioDecodeError(str(path), "no audio stream")
    stream = streams[0]
    if not isinstance(stream, dict):
        raise AudioDecodeError(str(path), "unreadable audio stream")
    try:
        sample_rate = int(str(stream.get("sample_rate", 0)))
        channels = int(str(stream.get("channels", 0)))
    except (TypeError, ValueError) as error:
        raise AudioDecodeError(str(path), "invalid sample rate or channel count") from error
    duration_raw = stream.get("duration")
    if duration_raw is None:
        format_info = data.get("format")
        if isinstance(format_info, dict):
            duration_raw = format_info.get("duration")
    try:
        duration = float(str(duration_raw))
    except (TypeError, ValueError) as error:
        raise AudioDecodeError(str(path), "invalid duration") from error
    if sample_rate <= 0 or channels <= 0 or duration < 0:
        raise AudioDecodeError(str(path), "invalid audio parameters")
    return Source(
        path=str(path.resolve()),
        sha256=sha256_of(path),
        duration_s=duration,
        sample_rate_hz=sample_rate,
        channels=channels,
    )
