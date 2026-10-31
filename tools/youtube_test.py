#!/usr/bin/env python3
"""Test mit einem echten Video: herunterladen, transkribieren, Untertitel einbrennen.

Aufruf:
    uv run python tools/youtube_test.py <URL> [--target de] [--out ordner]

Download mit yt-dlp. Nur für Aufnahmen verwenden, deren Nutzung erlaubt ist.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from transcriber import RunConfig, export, run_file
from transcriber.adapters.video import FfmpegVideoRenderer
from transcriber.registry import DEFAULT_REGISTRY


def download(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("yt-dlp")
    if not binary:
        raise SystemExit("yt-dlp fehlt")
    command = [
        binary,
        "-f",
        "bv*[height<=480]+ba/b[height<=480]",
        "--no-playlist",
        "-o",
        str(target_dir / "quelle.%(ext)s"),
        "--print",
        "after_move:filepath",
        url,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"yt-dlp fehlgeschlagen:\n{completed.stderr[-800:]}")
    printed = [line for line in completed.stdout.splitlines() if line.strip()]
    if not printed:
        raise SystemExit("yt-dlp hat keinen Pfad gemeldet")
    return Path(printed[-1])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--target", default="de")
    parser.add_argument("--out", default="out-youtube")
    parser.add_argument("--subtitle-lang", default=None)
    parser.add_argument("--gallery", default=None)
    args = parser.parse_args(argv[1:])

    out_dir = Path(args.out)
    video = download(args.url, out_dir)
    print(f"Video: {video} ({video.stat().st_size / 1e6:.1f} MB)")

    registry = DEFAULT_REGISTRY
    registry.discover()
    config = RunConfig(
        asr="faster-whisper",
        diarizer="pyannote",
        language_id="voxlingua",
        translator="madlad",
        voiceprint="wespeaker" if args.gallery else None,
        gallery=args.gallery,
        target_languages=[args.target],
    )

    started = time.perf_counter()
    transcript = run_file(video, config=config)
    elapsed = time.perf_counter() - started
    written = export(transcript, out_dir, formats=("json", "srt", "vtt", "txt"))
    (out_dir / "laufzeit.json").write_text(
        json.dumps({"sekunden": round(elapsed, 1), "dateien": [str(p) for p in written]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    speakers = {
        speaker.id: (speaker.name, speaker.segment_count) for speaker in transcript.speakers
    }
    languages = sorted({segment.language for segment in transcript.segments})
    print(f"\nSprecher: {len(speakers)} {speakers}")
    print(f"Sprachen: {languages}")
    print(f"Segmente: {len(transcript.segments)}, Dauer: {transcript.source.duration_s:.1f} s")
    print(f"Laufzeit: {elapsed:.1f} s")
    for segment in transcript.segments[:8]:
        print(f"  [{segment.start_s:6.1f}-{segment.end_s:6.1f}] {segment.speaker} "
              f"({segment.language}) {segment.text[:90]}")

    rendered = FfmpegVideoRenderer().render(
        video, transcript, out_dir / "untertitelt.mp4", args.subtitle_lang or args.target
    )
    print(f"\nVideo mit Untertiteln: {rendered}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
