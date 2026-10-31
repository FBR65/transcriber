"""S13, S14: Betriebsart stream. Ohne Mikrofon, ohne Modelle, mit Datei als Tonquelle."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from transcriber import RunConfig
from transcriber.cli import app
from transcriber.registry import Registry
from transcriber.stream import SpeakerTracker, run_stream

from .conftest import register_fake_adapters, write_wav


def write_speech_with_pauses(path: Path, parts: int = 3) -> Path:
    """Ton mit Stille dazwischen: der VAD muss mitten in der Einspeisung schneiden."""
    import math
    import struct
    import wave

    rate = 16000
    samples: list[int] = []
    for _ in range(parts):
        for index in range(int(1.0 * rate)):
            samples.append(int(0.3 * 32767 * math.sin(2 * math.pi * 440 * index / rate)))
        samples.extend([0] * int(0.7 * rate))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return path

runner = CliRunner()


def blocks(path: Path, block_s: float = 0.25) -> Iterator[np.ndarray]:
    from transcriber.adapters.source import iter_file

    yield from iter_file(path, block_s=block_s)


def config(**overrides: object) -> RunConfig:
    values: dict[str, object] = {
        "asr": "fake",
        "diarizer": "fake",
        "language_id": "fake",
        "translator": "fake",
        "voiceprint": None,
        "target_languages": ["fr"],
    }
    values.update(overrides)
    return RunConfig(**values)  # type: ignore[arg-type]


def registry() -> Registry:
    reg = Registry()
    register_fake_adapters(reg)
    from transcriber.adapters.source import EnergyVad

    reg.register("vad", "energy", EnergyVad)
    return reg


def test_events_arrive_before_the_feed_ends(tmp_path: Path) -> None:
    audio = write_speech_with_pauses(tmp_path / "strom.wav")
    total_blocks = 0
    blocks_at_first_event: list[int] = []

    def counted() -> Iterator[np.ndarray]:
        nonlocal total_blocks
        for block in blocks(audio):
            total_blocks += 1
            yield block

    events = []
    for event in run_stream(counted(), 16000, config=config(), registry=registry()):
        events.append(event)
        blocks_at_first_event.append(total_blocks)

    assert events, "kein Ereignis"
    assert blocks_at_first_event[0] < total_blocks, (
        "das erste Ereignis kam erst nach dem letzten Block"
    )
    for event in events:
        assert event.speaker.startswith("S")
        assert event.language
        assert event.text.strip()
        assert event.translations
        assert event.is_final is True


def test_translation_per_event(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "strom.wav", seconds=2.0)
    events = list(run_stream(blocks(audio), 16000, config=config(), registry=registry()))
    assert events
    for event in events:
        assert set(event.translations) == {"fr"}
        assert event.translations["fr"].startswith("[translated:fr]")


def test_speaker_tracker_separates_and_merges() -> None:
    tracker = SpeakerTracker(threshold=0.8)
    first, _ = tracker.assign(np.array([1.0, 0.0], dtype=np.float32))
    second, _ = tracker.assign(np.array([0.0, 1.0], dtype=np.float32))
    again, score = tracker.assign(np.array([0.99, 0.01], dtype=np.float32))
    assert first == "S1"
    assert second == "S2"
    assert again == "S1", f"ähnliche Stimme muss zurückfinden, Ähnlichkeit {score:.2f}"


def test_speaker_tracker_handles_zero_vector() -> None:
    tracker = SpeakerTracker()
    speaker, score = tracker.assign(np.zeros(4, dtype=np.float32))
    assert speaker == "S1"
    assert score == 0.0


def test_cli_stream_writes_jsonl(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "strom.wav", seconds=3.0)
    config_path = tmp_path / "c.toml"
    config_path.write_text(
        '[adapters]\nasr="fake"\ndiarizer="fake"\nlanguage_id="fake"\n'
        'translator="fake"\nvoiceprint=""\n\n[targets]\nlanguages=["fr"]\n',
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["stream", "--source", str(audio), "--config", str(config_path), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    lines = (out / "ereignisse.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[0])
    assert payload["is_final"] is True
    assert payload["translations"]


def test_cli_stream_reports_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["stream", "--source", str(tmp_path / "fehlt.wav"), "--out", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "fehlt.wav" in result.output


def test_silence_produces_no_events(tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "still.wav", seconds=2.0, amplitude=0.0)
    events = list(run_stream(blocks(audio), 16000, config=config(), registry=registry()))
    assert events == []
