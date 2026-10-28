"""S7: Export nach json, srt, vtt, txt."""

from __future__ import annotations

import json
from pathlib import Path

from transcriber import Registry, RunConfig, export, run_file

from .conftest import register_fake_adapters


def test_export_formats(tmp_path: Path, audio_file: Path) -> None:
    registry = Registry()
    register_fake_adapters(registry)
    config = RunConfig(
        asr="fake",
        diarizer="fake",
        language_id="fake",
        translator="fake",
        target_languages=["fr"],
    )
    transcript = run_file(audio_file, config=config, registry=registry)

    written = export(transcript, tmp_path / "out", formats=("json", "srt", "vtt", "txt"))
    names = {path.name.split(".")[-1] for path in written}
    assert names == {"json", "srt", "vtt", "txt"}

    for path in written:
        assert path.is_file()
        assert path.read_text(encoding="utf-8").strip()

    data = json.loads((tmp_path / "out" / "probe.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["segments"]) == len(transcript.segments)

    srt = (tmp_path / "out" / "probe.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "S1" in srt

    vtt = (tmp_path / "out" / "probe.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in vtt

    txt = (tmp_path / "out" / "probe.txt").read_text(encoding="utf-8")
    assert "S1" in txt
    assert "Hallo Welt" in txt
