"""Ton für die Sprach-ID. PyAV, kein torchaudio (torchaudio 2.11 hat `load`/`info` entfernt)."""

from __future__ import annotations

from pathlib import Path

import av
import numpy as np

TARGET_RATE = 16_000


def load_mono_16k(path: Path, target_rate: int = TARGET_RATE) -> np.ndarray:
    """Ganze Datei als mono float32 bei 16 kHz."""
    chunks: list[np.ndarray] = []
    try:
        with av.open(str(path), mode="r", metadata_errors="ignore") as container:
            if not container.streams.audio:
                raise ValueError(f"no audio stream in {path}")
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="flt", layout="mono", rate=target_rate)
            for frame in container.decode(stream):
                for resampled in resampler.resample(frame):
                    chunks.append(resampled.to_ndarray().reshape(-1))
            for resampled in resampler.resample(None):
                chunks.append(resampled.to_ndarray().reshape(-1))
    except (av.error.FFmpegError, OSError) as error:
        raise ValueError(f"cannot decode audio file {path}: {error}") from error
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32, copy=False)


def slice_seconds(
    samples: np.ndarray, start_s: float, end_s: float, sample_rate: int = TARGET_RATE
) -> np.ndarray:
    """Schneidet einen Zeitbereich heraus. Grenzen werden auf die Länge begrenzt."""
    total = len(samples)
    begin = min(max(0, int(start_s * sample_rate)), total)
    end = min(total, max(begin, int(end_s * sample_rate)))
    return samples[begin:end]
