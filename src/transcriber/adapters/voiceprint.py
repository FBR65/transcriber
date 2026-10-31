"""Stimmabdruck über weSpeaker (pyannote) und die lokale Galerie (SPEC Abschnitt 7)."""

from __future__ import annotations

from pathlib import Path

import numpy

from ..gallery import Gallery
from ..ports import PersonInfo, VoiceprintMatch
from .builtin import _allow_torch_version_global, _patch_hub_compatibility

MODEL_ID = "pyannote/wespeaker-voxceleb-resnet34-LM"


class WeSpeakerVoiceprint:
    """Erzeugt Stimmabdrücke und vergleicht sie mit der Galerie."""

    def __init__(
        self,
        gallery: str | Path | None = None,
        threshold: float = 0.70,
        model: str = MODEL_ID,
        device: str = "cuda",
    ) -> None:
        import torch
        from pyannote.audio import Inference, Model

        _patch_hub_compatibility()
        _allow_torch_version_global()
        self._torch = torch
        self._model = Model.from_pretrained(model)
        self._inference = Inference(
            self._model, window="whole", device=torch.device(device)
        )
        self._gallery = Gallery(Path(gallery) if gallery else None, threshold=threshold)
        self._model_name = model

    @property
    def gallery(self) -> Gallery:
        return self._gallery

    def _embedding(self, path: Path, start_s: float, end_s: float) -> numpy.ndarray:
        from pyannote.core import Segment

        if end_s <= start_s:
            raise ValueError("segment must have a positive length")
        embedding = self._inference.crop(str(path), Segment(start_s, end_s))
        return numpy.asarray(embedding, dtype=numpy.float32).reshape(-1)

    def identify(self, path: Path, start_s: float, end_s: float) -> VoiceprintMatch | None:
        return self._gallery.match(self._embedding(path, start_s, end_s))

    def enroll(
        self, path: Path, start_s: float, end_s: float, name: str, *, consent: bool
    ) -> PersonInfo:
        embedding = self._embedding(path, start_s, end_s)
        return self._gallery.add(
            name,
            embedding,
            consent=consent,
            source=f"{Path(path).name}@{start_s:.2f}-{end_s:.2f}",
            model=self._model_name,
        )

    def delete(self, reference: str) -> int:
        return self._gallery.delete(reference)

    def people(self) -> list[PersonInfo]:
        return self._gallery.people()

    def release(self) -> None:
        self._model = None
        self._inference = None

