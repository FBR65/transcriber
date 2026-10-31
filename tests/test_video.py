"""S20: Untertitel einbrennen. Echte Dateien, echte ffmpeg-Aufrufe, keine Modelle."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import av
import numpy as np
import pytest

from transcriber import RunConfig, Segment, Source, SpeakerInfo, Transcript
from transcriber.adapters.video import FfmpegVideoRenderer
from transcriber.errors import VideoRenderError

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def make_video(path: Path, seconds: float = 3.0) -> Path:
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=10:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


def make_transcript() -> Transcript:
    segments = [
        Segment(
            id="seg-0001",
            start_s=0.0,
            end_s=1.0,
            speaker="S1",
            language="en",
            language_confidence=0.9,
            text="Hello world",
            translations={"de": "Hallo Welt"},
        ),
        Segment(
            id="seg-0002",
            start_s=1.2,
            end_s=2.2,
            speaker="S2",
            language="en",
            language_confidence=0.9,
            text="Second speaker",
            translations={"de": "Zweiter Sprecher"},
        ),
    ]
    return Transcript(
        created_at=datetime.now(UTC).replace(microsecond=0),
        source=Source(path="/tmp/x.mp4", sha256="0" * 64, duration_s=3.0,
                      sample_rate_hz=16000, channels=1),
        config=RunConfig(asr="a", diarizer="b", language_id="c", translator="d",
                         target_languages=["de"]),
        speakers=[
            SpeakerInfo(id="S1", speech_s=1.0, segment_count=1),
            SpeakerInfo(id="S2", speech_s=1.0, segment_count=1),
        ],
        segments=segments,
    )


def streams(path: Path) -> list[dict[str, object]]:
    probe = shutil.which("ffprobe") or "ffprobe"
    output = subprocess.run(
        [probe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    import json

    return list(json.loads(output)["streams"])


def frame(path: Path, seconds: float) -> np.ndarray:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        container.seek(int(seconds * 1_000_000), stream=stream, backward=True)
        for picture in container.decode(stream):
            if picture.pts is None:
                continue
            if picture.time_base is None:
                continue
            moment = float(picture.pts * picture.time_base)
            if moment >= seconds:
                return picture.to_ndarray(format="rgb24")
    raise AssertionError(f"kein Bild bei {seconds}s in {path}")


def test_command_contains_libass_filter() -> None:
    renderer = FfmpegVideoRenderer(font_size=30, margin_v=55)
    command = renderer.build_command(Path("in.mp4"), "untertitel.srt", Path("out.mp4"))
    joined = " ".join(command)
    assert "subtitles=untertitel.srt" in joined
    assert "FontSize=30" in joined
    assert "MarginV=55" in joined
    assert "libx264" in joined
    assert command[-1] == "out.mp4"


def test_burned_in_subtitles(tmp_path: Path) -> None:
    video = make_video(tmp_path / "quelle.mp4", seconds=3.0)
    out = tmp_path / "untertitelt.mp4"
    renderer = FfmpegVideoRenderer()
    result = renderer.render(video, make_transcript(), out, language="de")

    assert result == out
    assert out.is_file() and out.stat().st_size > 0

    kinds = {stream["codec_type"] for stream in streams(out)}
    assert kinds == {"video", "audio"}, kinds

    source_streams = streams(video)
    target_streams = streams(out)
    source_duration = float(str(source_streams[0]["duration"]))
    target_duration = float(str(target_streams[0]["duration"]))
    assert abs(target_duration - source_duration) <= 0.1, (target_duration, source_duration)

    # Im Untertitelbereich muss sich das Bild ändern, im oberen Bereich nicht.
    before = frame(video, 0.5)
    after = frame(out, 0.5)
    height = before.shape[0]
    lower_before = before[int(height * 0.75) :, :, :].astype(np.int16)
    lower_after = after[int(height * 0.75) :, :, :].astype(np.int16)
    upper_before = before[: int(height * 0.25), :, :].astype(np.int16)
    upper_after = after[: int(height * 0.25), :, :].astype(np.int16)

    lower_diff = float(np.abs(lower_before - lower_after).mean())
    upper_diff = float(np.abs(upper_before - upper_after).mean())
    assert lower_diff > upper_diff * 2, (
        f"unten {lower_diff:.1f}, oben {upper_diff:.1f} — keine Untertitel erkennbar"
    )


def test_audio_stream_is_kept(tmp_path: Path) -> None:
    video = make_video(tmp_path / "quelle.mp4", seconds=2.0)
    out = tmp_path / "mit-ton.mp4"
    FfmpegVideoRenderer().render(video, make_transcript(), out)
    audio = [stream for stream in streams(out) if stream["codec_type"] == "audio"]
    assert audio, "Tonspur fehlt"


def test_missing_video_is_reported(tmp_path: Path) -> None:
    with pytest.raises(VideoRenderError):
        FfmpegVideoRenderer().render(
            tmp_path / "fehlt.mp4", make_transcript(), tmp_path / "out.mp4"
        )


def test_empty_transcript_is_reported(tmp_path: Path) -> None:
    video = make_video(tmp_path / "quelle.mp4", seconds=1.0)
    empty = make_transcript().model_copy(update={"segments": []})
    with pytest.raises(VideoRenderError):
        FfmpegVideoRenderer().render(video, empty, tmp_path / "out.mp4")


def test_unknown_subtitle_language_is_reported(tmp_path: Path) -> None:
    video = make_video(tmp_path / "quelle.mp4", seconds=1.0)
    with pytest.raises(VideoRenderError):
        FfmpegVideoRenderer().render(
            video, make_transcript(), tmp_path / "out.mp4", language="fr"
        )
