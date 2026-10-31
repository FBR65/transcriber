"""Betriebsart `stream`: laufender Ton, Ereignisse während der Einspeisung (SPEC S13, S14).

Der Kern kennt nur Ports. Die Blöcke kommen als float32-Arrays bei 16 kHz, mono.
"""

from __future__ import annotations

import tempfile
import wave
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import DEFAULT_ADAPTERS
from .models import RunConfig
from .registry import DEFAULT_REGISTRY, Registry


@dataclass(frozen=True, slots=True)
class StreamEvent:
    index: int
    start_s: float
    end_s: float
    speaker: str
    language: str
    language_confidence: float
    text: str
    translations: dict[str, str]
    translated_from: str | None = None
    is_final: bool = True


@dataclass(slots=True)
class SpeakerTracker:
    """Ordnet jeden Abschnitt dem ähnlichsten Sprecher zu und lernt dessen Mittelwert."""

    threshold: float = 0.75
    centroids: dict[str, np.ndarray] = field(default_factory=dict)

    def assign(self, embedding: np.ndarray) -> tuple[str, float]:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return self._new(vector), 0.0
        vector = vector / norm
        best_id: str | None = None
        best_score = -1.0
        for speaker_id, centroid in self.centroids.items():
            score = float(np.dot(vector, centroid))
            if score > best_score:
                best_score, best_id = score, speaker_id
        if best_id is None or best_score < self.threshold:
            return self._new(vector), best_score
        updated = 0.7 * self.centroids[best_id] + 0.3 * vector
        self.centroids[best_id] = updated / float(np.linalg.norm(updated))
        return best_id, best_score

    def _new(self, vector: np.ndarray) -> str:
        speaker_id = f"S{len(self.centroids) + 1}"
        self.centroids[speaker_id] = vector
        return speaker_id


def _write_wav(samples: np.ndarray, path: Path, sample_rate: int) -> Path:
    clipped = np.clip(samples, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((clipped * 32767).astype("<i2").tobytes())
    return path


def run_stream(
    blocks: Iterable[np.ndarray],
    sample_rate: int,
    *,
    config: RunConfig | None = None,
    registry: Registry | None = None,
    lang: str = "de",
    translate: bool = True,
) -> Iterator[StreamEvent]:
    """Verarbeitet Tonblöcke und liefert fertige Ereignisse, während Ton ankommt."""
    reg = registry or DEFAULT_REGISTRY
    cfg = config or RunConfig(**DEFAULT_ADAPTERS, target_languages=["de"])
    vad = reg.create("vad", "energy")
    asr = reg.create("asr", cfg.asr)
    language_id = reg.create("language_id", cfg.language_id)
    # Auf 8 GB VRAM passen Whisper und ein 3B-Übersetzer nicht zusammen. Ohne Übersetzung
    # bleibt der Übersetzer ungeladen.
    translator = reg.create("translator", cfg.translator) if translate else None
    embedder = reg.create("embedder", "wespeaker") if cfg.voiceprint else None
    tracker = SpeakerTracker()

    buffer = np.zeros(0, dtype=np.float32)
    emitted_until = 0.0
    index = 0
    previous_language: str | None = None

    def handle(start_s: float, end_s: float, samples: np.ndarray) -> StreamEvent | None:
        nonlocal index, previous_language
        with tempfile.TemporaryDirectory(prefix="transcriber-stream-") as workdir:
            path = _write_wav(samples, Path(workdir) / "block.wav", sample_rate)
            segments = list(asr.transcribe(path))
            if not segments:
                return None
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if not text:
                return None
            language, confidence = language_id.detect(path, 0.0, float(samples.size / sample_rate))
            if confidence < 0.5 and previous_language:
                language, confidence = previous_language, 0.5
            previous_language = language
            speaker = "S1"
            if embedder is not None:
                speaker, _score = tracker.assign(embedder.embed(path, 0.0, end_s - start_s))

        translations: dict[str, str] = {}
        if translator is None:
            translations[language] = text
        else:
            for target in cfg.target_languages:
                if target == language:
                    translations[target] = text
                else:
                    result = list(translator.translate([text], language, target))
                    translations[target] = result[0] if result else ""
        changed = any(value != text for value in translations.values())
        index += 1
        return StreamEvent(
            index=index,
            start_s=start_s,
            end_s=end_s,
            speaker=speaker,
            language=language,
            language_confidence=confidence,
            text=text,
            translations=translations,
            translated_from=language if changed else None,
        )

    try:
        for block in blocks:
            buffer = np.concatenate([buffer, np.asarray(block, dtype=np.float32).reshape(-1)])
            duration = buffer.size / sample_rate
            for start_s, end_s in vad.completed_spans(buffer, sample_rate):
                if start_s < emitted_until:
                    continue
                begin = int(start_s * sample_rate)
                end = int(end_s * sample_rate)
                event = handle(start_s, end_s, buffer[begin:end].copy())
                emitted_until = end_s
                if event is not None:
                    yield event
            duration = buffer.size / sample_rate
            if duration > 120.0:  # Speicher begrenzen: alten Ton verwerfen
                keep_from = int(emitted_until * sample_rate)
                buffer = buffer[keep_from:]
        # Rest am Ende
        duration = buffer.size / sample_rate
        begin = int(emitted_until * sample_rate)
        rest = buffer[begin:]
        if rest.size > int(0.2 * sample_rate) and vad.has_speech(rest, sample_rate):
            event = handle(emitted_until, duration, rest)
            if event is not None:
                yield event
    finally:
        from .core import release

        for adapter in (vad, asr, language_id, translator, embedder):
            if adapter is not None:
                release(adapter)
