"""Sprachaktivität (VAD) und Tonquellen für die Betriebsart `stream`."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000


class EnergyVad:
    """Einfacher Energie-VAD. Kein Modell, überall verfügbar, gut prüfbar.

    Liefert Abschnitte, die von mindestens `min_silence_s` Stille abgeschlossen sind.
    """

    def __init__(
        self,
        threshold: float = 0.01,
        min_silence_s: float = 0.35,
        min_speech_s: float = 0.35,
        max_speech_s: float = 15.0,
    ) -> None:
        self.threshold = threshold
        self.min_silence_s = min_silence_s
        self.min_speech_s = min_speech_s
        self.max_speech_s = max_speech_s

    def has_speech(self, samples: np.ndarray, sample_rate: int) -> bool:
        if samples.size == 0:
            return False
        return bool(float(np.abs(samples).max()) >= self.threshold)

    def completed_spans(self, samples: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
        frame = int(0.05 * sample_rate)
        if samples.size < frame:
            return []
        frames = samples.size // frame
        energy = np.abs(samples[: frames * frame]).reshape(frames, frame).max(axis=1)
        loud = energy >= self.threshold

        spans: list[tuple[float, float]] = []
        start: int | None = None
        silent_frames = 0
        silence_needed = max(1, int(self.min_silence_s / 0.05))
        min_frames = max(1, int(self.min_speech_s / 0.05))
        max_frames = max(1, int(self.max_speech_s / 0.05))

        for index, is_loud in enumerate(loud):
            if is_loud:
                if start is None:
                    start = index
                silent_frames = 0
                if index - start + 1 >= max_frames:
                    spans.append((start * 0.05, (index + 1) * 0.05))
                    start = None
            elif start is not None:
                silent_frames += 1
                if silent_frames >= silence_needed:
                    end_frame = index - silent_frames + 1
                    if end_frame - start >= min_frames:
                        spans.append((start * 0.05, end_frame * 0.05))
                    start = None
                    silent_frames = 0
        return spans


class SileroVad:
    """Sprachaktivität mit Silero. Braucht torch, wird erst beim Erzeugen geladen."""

    def __init__(self, threshold: float = 0.5, min_silence_s: float = 0.35) -> None:
        import torch

        self._torch = torch
        model, _utils = torch.hub.load(  # type: ignore[no-untyped-call]
            repo_or_dir="snakers4/silero-vad", model="silero_vad", onnx=False, trust_repo=True
        )
        self._model = model
        self.threshold = threshold
        self.min_silence_s = min_silence_s

    def has_speech(self, samples: np.ndarray, sample_rate: int) -> bool:
        return bool(samples.size) and bool(float(np.abs(samples).max()) >= 0.01)

    def completed_spans(self, samples: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
        chunk = 512 if sample_rate == 16_000 else 256
        spans: list[tuple[float, float]] = []
        tensor = self._torch.from_numpy(samples.copy()).unsqueeze(0)
        speech = self._model.audio_forward(tensor, sample_rate)
        flags = speech.reshape(-1) >= self.threshold
        step = len(samples) / max(1, flags.numel()) if flags.numel() else 0.0
        start: float | None = None
        for index, is_speech in enumerate(flags.tolist()):
            moment = index * step
            if is_speech and start is None:
                start = moment
            elif not is_speech and start is not None:
                if moment - start >= 0.35:
                    spans.append((start, moment))
                start = None
        del chunk
        return spans


def iter_file(
    path: Path, block_s: float = 0.5, sample_rate: int = SAMPLE_RATE
) -> Iterator[np.ndarray]:
    """Liest eine Datei blockweise als mono float32 bei 16 kHz (über ffmpeg)."""
    binary = "ffmpeg"
    command = [
        binary, "-v", "error", "-i", str(path), "-vn", "-ac", "1",
        "-ar", str(sample_rate), "-f", "f32le", "-",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if process.stdout is None:  # pragma: no cover - defensiv
            raise RuntimeError("no stdout")
        block_bytes = int(block_s * sample_rate) * 4
        while True:
            raw = process.stdout.read(block_bytes)
            if not raw:
                break
            yield np.frombuffer(raw, dtype=np.float32).copy()
    finally:
        process.terminate()
        process.wait(timeout=10)


def iter_mic(block_s: float = 0.5, sample_rate: int = SAMPLE_RATE) -> Iterator[np.ndarray]:
    """Liest vom Mikrofon. Nicht ohne Eingabegerät prüfbar."""
    import sounddevice as sd

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
        while True:
            data, _overflow = stream.read(int(block_s * sample_rate))
            yield np.asarray(data, dtype=np.float32).reshape(-1)
