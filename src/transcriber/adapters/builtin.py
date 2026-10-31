"""Standardadapter. Jedes Modell wird erst beim Erzeugen importiert (kein ML-Code im Kern)."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ..ports import AsrSegment, SpeakerTurn
from ..registry import Registry
from .mapping import (
    is_supported_target,
    language_code,
    madlad_languages,
    madlad_prompt,
    segments_from_whisper,
    turns_from_annotation,
)

SAMPLE_RATE = 16_000


class WhisperAsr:
    """faster-whisper, large-v3 als Standard (SPEC D1 = a)."""

    def __init__(
        self,
        model: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        beam_size: int = 5,
    ) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model, device=device, compute_type=compute_type)
        self._beam_size = beam_size

    def transcribe(
        self, path: Path, options: Mapping[str, Any] | None = None
    ) -> Sequence[AsrSegment]:
        # Die Sprache je Abschnitt erkennt der Sprach-ID-Adapter; Whisper liefert nur eine
        # Sprache für die ganze Datei.
        segments, _info = self._model.transcribe(
            str(path), beam_size=self._beam_size, vad_filter=True
        )
        return segments_from_whisper(segments, None)

    def release(self) -> None:
        self._model = None


def _hf_token(explicit: str | None) -> str | None:
    """Token aus Argument, Umgebung oder der Datei, die huggingface_hub selbst nutzt."""
    if explicit:
        return explicit
    from_env = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if from_env:
        return from_env.strip()
    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if token_file.is_file():
        value = token_file.read_text(encoding="utf-8").strip()
        return value or None
    return None


def _token_shim(original: Any, accepts_use_auth_token: bool) -> Any:
    """pyannote 3.x übergibt `use_auth_token`, huggingface_hub 2.x nur noch `token`."""
    if accepts_use_auth_token:
        return original

    def forward(*args: Any, use_auth_token: Any = None, **kwargs: Any) -> Any:
        if use_auth_token is not None and "token" not in kwargs:
            kwargs["token"] = use_auth_token
        return original(*args, **kwargs)

    return forward


def _patch_hub_compatibility() -> None:
    """Hängt vor jeden bereits gebundenen `hf_hub_download` einen Token-Übersetzer.

    pyannote 3.x ruft `hf_hub_download(..., use_auth_token=...)`. huggingface_hub 2.x kennt
    das Argument nicht mehr. Weil pyannote die Funktion an mehreren Stellen importiert,
    werden alle gebundenen Namen ersetzt, nicht nur das Paketattribut.
    """
    import inspect
    import sys

    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        if name != "huggingface_hub" and not name.startswith(("huggingface_hub.", "pyannote")):
            continue
        candidate = getattr(module, "hf_hub_download", None)
        if candidate is None or not callable(candidate):
            continue
        if getattr(candidate, "_transcriber_token_shim", False):
            continue
        try:
            parameters = inspect.signature(candidate).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotische Aufrufobjekte
            continue
        if "use_auth_token" in parameters:
            continue
        shim = _token_shim(candidate, False)
        module.hf_hub_download = shim  # type: ignore[attr-defined]
        shim._transcriber_token_shim = True


def _allow_torch_version_global() -> None:
    """pyannote-Checkpoints enthalten Klassen, die torch ≥ 2.6 sonst ablehnt.

    Es sind reine Metadaten-Klassen aus pyannote selbst (Version, Problem, Auflösung, Task).
    """
    import torch

    allowlist = getattr(torch.serialization, "add_safe_globals", None)
    if not callable(allowlist):
        return
    allowed: list[object] = []
    version_type = getattr(getattr(torch, "torch_version", None), "TorchVersion", None)
    if version_type is not None:
        allowed.append(version_type)
    try:
        from pyannote.audio.core import task as pyannote_task

        for name in ("Specifications", "Problem", "Resolution", "Task"):
            candidate = getattr(pyannote_task, name, None)
            if candidate is not None:
                allowed.append(candidate)
    except ImportError:  # pragma: no cover - pyannote fehlt
        pass
    if allowed:
        allowlist(allowed)


class PyannoteDiarizer:
    """pyannote.audio mit der Pipeline speaker-diarization-3.1 (SPEC D2)."""

    def __init__(
        self,
        model: str = "pyannote/speaker-diarization-3.1",
        device: str = "cuda",
        token: str | None = None,
    ) -> None:
        from pyannote.audio import Pipeline

        _patch_hub_compatibility()
        _allow_torch_version_global()
        resolved = _hf_token(token)
        if resolved:
            # pyannote 3.x kennt kein `token`-Argument, 4.x schon. Die Umgebungsvariable
            # funktioniert in beiden Fassungen.
            os.environ.setdefault("HF_TOKEN", resolved)
        self._pipeline = Pipeline.from_pretrained(model)
        self._device = device

    def diarize(
        self, path: Path, options: Mapping[str, Any] | None = None
    ) -> Sequence[SpeakerTurn]:
        import torch

        if self._device:
            self._pipeline.to(torch.device(self._device))
        output = self._pipeline(str(path))
        # pyannote 4.x liefert ein Objekt mit speaker_diarization, 3.x direkt die Annotation.
        annotation = getattr(output, "speaker_diarization", output)
        raw = [
            (segment.start, segment.end, label)
            for segment, _, label in annotation.itertracks(yield_label=True)
        ]
        return turns_from_annotation(raw)

    def release(self) -> None:
        self._pipeline = None


class VoxLinguaLanguageId:
    """Sprache je Abschnitt mit dem ECAPA-Modell auf VoxLingua107 (SPEC 3)."""

    def __init__(
        self,
        model: str = "speechbrain/lang-id-voxlingua107-ecapa",
        device: str = "cuda",
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        from speechbrain.inference.classifiers import EncoderClassifier

        self._classifier = EncoderClassifier.from_hparams(
            source=model, run_opts={"device": device}, savedir=None
        )
        self._sample_rate = sample_rate
        self._samples: np.ndarray | None = None
        self._samples_path: str | None = None

    def detect(self, path: Path, start_s: float, end_s: float) -> tuple[str, float]:
        import torch

        from .audio_io import load_mono_16k, slice_seconds

        if self._samples is None or self._samples_path != str(path):
            self._samples = load_mono_16k(path, self._sample_rate)
            self._samples_path = str(path)
        chunk = slice_seconds(self._samples, start_s, end_s, self._sample_rate)
        if chunk.size == 0:
            return "und", 0.0
        waveform = torch.from_numpy(chunk).unsqueeze(0)
        _prob, score, _index, labels = self._classifier.classify_batch(waveform)
        label = labels[0] if isinstance(labels, list) else str(labels)
        value = float(score[0]) if hasattr(score, "__len__") else float(score)
        confidence = math.exp(min(0.0, value))
        return language_code(label), max(0.0, min(1.0, confidence))

    def release(self) -> None:
        self._classifier = None
        self._samples = None


class MadladTranslator:
    """MADLAD-400-3B-MT über transformers (SPEC D3 = a)."""

    def __init__(
        self,
        model: str = "google/madlad400-3b-mt",
        device: str = "cuda",
        dtype: str = "bfloat16",
        batch_size: int = 8,
        max_new_tokens: int = 256,
    ) -> None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self._torch = torch
        self._device = device
        torch_dtype = getattr(torch, dtype)
        self._tokenizer = AutoTokenizer.from_pretrained(model)
        # device_map lädt Gewicht für Gewicht auf die GPU. Ohne das liegt die fp32-Kopie
        # zusätzlich im RAM und der Lauf stirbt an Speichermangel.
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            model,
            dtype=torch_dtype,
            device_map=None if device == "cpu" else device,
            low_cpu_mem_usage=True,
        )
        if device == "cpu":
            self._model = self._model.to(device)
        self._model.eval()
        self._batch_size = batch_size
        self._max_new_tokens = max_new_tokens

    def languages(self) -> set[str]:
        return madlad_languages()

    def translate(
        self, texts: Sequence[str], source_lang: str, target_lang: str
    ) -> Sequence[str]:
        if not is_supported_target(target_lang):
            raise ValueError(f"target language {target_lang!r} is not covered by this model")
        results: list[str] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            prompts = [madlad_prompt(target_lang, text) for text in batch]
            encoded = self._tokenizer(prompts, return_tensors="pt", padding=True).to(self._device)
            with self._torch.inference_mode():
                generated = self._model.generate(
                    **encoded, max_new_tokens=self._max_new_tokens, num_beams=4
                )
            results.extend(
                self._tokenizer.batch_decode(generated, skip_special_tokens=True)
            )
        return results

    def release(self) -> None:
        self._model = None
        self._torch.cuda.empty_cache()


def register(registry: Registry) -> None:
    """Meldet die Standardadapter an. Wird über den Einstiegspunkt geladen."""
    from .video import FfmpegVideoRenderer
    from .voiceprint import WeSpeakerVoiceprint

    registry.register("asr", "faster-whisper", WhisperAsr)
    registry.register("diarizer", "pyannote", PyannoteDiarizer)
    registry.register("language_id", "voxlingua", VoxLinguaLanguageId)
    registry.register("translator", "madlad", MadladTranslator)
    registry.register("voiceprint", "wespeaker", WeSpeakerVoiceprint)
    registry.register("video_renderer", "ffmpeg", FfmpegVideoRenderer)
