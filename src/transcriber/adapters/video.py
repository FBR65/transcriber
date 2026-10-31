"""Untertitel in ein Video einbrennen (SPEC D12 = b, Abnahme S20).

ffmpeg mit libass. Der Untertitel wird als SRT im Arbeitsordner abgelegt, damit im
Filter keine Pfade mit Sonderzeichen stehen müssen.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import VideoRenderError
from ..exporters import write_srt
from ..models import Transcript


class FfmpegVideoRenderer:
    def __init__(
        self,
        binary: str | None = None,
        font_size: int = 22,
        margin_v: int = 40,
        crf: int = 20,
        preset: str = "veryfast",
    ) -> None:
        self._binary = binary or shutil.which("ffmpeg") or "ffmpeg"
        self._font_size = font_size
        self._margin_v = margin_v
        self._crf = crf
        self._preset = preset

    def _filter(self, subtitle_file: str) -> str:
        style = (
            f"FontSize={self._font_size},MarginV={self._margin_v},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2"
        )
        return f"subtitles={subtitle_file}:force_style='{style}'"

    def build_command(
        self, video: Path, subtitle_file: str, out: Path
    ) -> list[str]:
        """Der Befehl ist eine reine Funktion, damit er ohne ffmpeg prüfbar ist."""
        return [
            self._binary,
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            self._filter(subtitle_file),
            "-c:v",
            "libx264",
            "-crf",
            str(self._crf),
            "-preset",
            self._preset,
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(out),
        ]

    def render(
        self, video: Path, transcript: Transcript, out: Path, language: str | None = None
    ) -> Path:
        video = Path(video)
        out = Path(out)
        if not video.is_file():
            raise VideoRenderError(str(video), "file not found")
        if not transcript.segments:
            raise VideoRenderError(str(video), "transcript has no segments")
        if language is not None and transcript.segments[0].translations:
            available = set(transcript.segments[0].translations)
            if language not in available:
                raise VideoRenderError(
                    str(video), f"language {language!r} not in transcript: {sorted(available)}"
                )
        out.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="transcriber-subs-") as workdir:
            subtitle_name = "untertitel.srt"
            subtitle_path = Path(workdir) / subtitle_name
            write_srt(transcript, subtitle_path, language=language)
            # Absolut, weil ffmpeg im Arbeitsordner läuft (dort liegt die SRT).
            command = self.build_command(video.resolve(), subtitle_name, out.resolve())
            completed = subprocess.run(
                command, cwd=workdir, capture_output=True, text=True, check=False
            )
        if completed.returncode != 0:
            raise VideoRenderError(str(video), (completed.stderr or "ffmpeg failed").strip()[:300])
        if not out.is_file() or out.stat().st_size == 0:
            raise VideoRenderError(str(video), "no output written")
        return out
