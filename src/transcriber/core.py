"""Kern: führt einen Lauf aus. Kennt nur Ports, keine Modelle."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .audio import probe
from .config import DEFAULT_ADAPTERS
from .errors import UnsupportedLanguageError
from .i18n import translate
from .models import RunConfig, Segment, SpeakerInfo, Transcript
from .registry import DEFAULT_REGISTRY, Registry

Turn = tuple[float, float, str]


@dataclass(slots=True)
class Draft:
    """Ein Abschnitt vor der Übersetzung."""

    index: int
    start_s: float
    end_s: float
    speaker: str
    language: str
    language_confidence: float
    text: str


def assign_speakers(start_s: float, end_s: float, turns: Sequence[Turn]) -> str | None:
    """Sprecher mit der größten zeitlichen Überschneidung. Bei Gleichstand: frühester Beginn."""
    if not turns:
        return None
    best_label = turns[0][2]
    best_overlap = float("-inf")
    best_start = turns[0][0]
    for turn_start, turn_end, label in turns:
        overlap = min(end_s, turn_end) - max(start_s, turn_start)
        if overlap > best_overlap or (overlap == best_overlap and turn_start < best_start):
            best_overlap = overlap
            best_start = turn_start
            best_label = label
    if best_overlap <= 0.0:
        # Kein Kontakt: den Sprecher mit dem nächsten Mittelpunkt nehmen.
        middle = (start_s + end_s) / 2
        best_label = min(turns, key=lambda turn: abs((turn[0] + turn[1]) / 2 - middle))[2]
    return best_label


def _normalize(labels: Sequence[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for label in labels:
        if label not in mapping:
            mapping[label] = f"S{len(mapping) + 1}"
    return mapping


def _drafts(
    raw: Sequence[Any],
    turns: Sequence[Turn],
    mapping: dict[str, str],
    language_id: Any,
    audio_path: Path,
) -> list[Draft]:
    drafts: list[Draft] = []
    for index, item in enumerate(raw, start=1):
        start_s = float(item.start_s)
        end_s = float(item.end_s)
        label = assign_speakers(start_s, end_s, turns) or "S1"
        language = getattr(item, "language", None)
        if language:
            detected, confidence = str(language), 1.0
        else:
            detected, confidence = language_id.detect(audio_path, start_s, end_s)
        drafts.append(
            Draft(
                index=index,
                start_s=start_s,
                end_s=end_s,
                speaker=mapping.get(label, label),
                language=str(detected),
                language_confidence=max(0.0, min(1.0, float(confidence))),
                text=str(item.text),
            )
        )
    return drafts


def release(adapter: object) -> None:
    """Gibt Speicher frei, wenn der Adapter das kann. Der Kern kennt kein ML."""
    hook = getattr(adapter, "release", None)
    if callable(hook):
        hook()


def run_file(
    path: Path | str,
    *,
    config: RunConfig | None = None,
    registry: Registry | None = None,
    lang: str = "de",
) -> Transcript:
    """Ein Lauf über eine Datei. Liefert ein geprüftes Transkript."""
    reg = registry or DEFAULT_REGISTRY
    cfg = config or RunConfig(**DEFAULT_ADAPTERS, target_languages=["de"])
    source = probe(Path(path))
    audio_path = Path(source.path or str(path))

    asr = reg.create("asr", cfg.asr)
    try:
        raw = list(asr.transcribe(audio_path))
    finally:
        release(asr)

    diarizer = reg.create("diarizer", cfg.diarizer)
    try:
        turns: list[Turn] = [
            (turn.start_s, turn.end_s, turn.speaker) for turn in diarizer.diarize(audio_path)
        ]
    finally:
        release(diarizer)
    if not turns and raw:
        turns = [(0.0, source.duration_s, "S1")]
    mapping = _normalize([label for _, _, label in turns])

    if cfg.voiceprint:
        reg.create("voiceprint", cfg.voiceprint)

    language_id = None
    needs_language_id = any(getattr(item, "language", None) is None for item in raw)
    try:
        if needs_language_id:
            language_id = reg.create("language_id", cfg.language_id)
            drafts = _drafts(raw, turns, mapping, language_id, audio_path)
        else:
            drafts = _drafts(raw, turns, mapping, None, audio_path)
    finally:
        if language_id is not None:
            release(language_id)

    translations: dict[int, dict[str, str]] = {draft.index: {} for draft in drafts}
    if drafts:
        translator = reg.create("translator", cfg.translator)
        try:
            available = sorted(translator.languages())
            for target in cfg.target_languages:
                if target not in available:
                    raise UnsupportedLanguageError(target, available)
            for target in cfg.target_languages:
                batches: dict[str, list[Draft]] = {}
                for draft in drafts:
                    if draft.language == target:
                        translations[draft.index][target] = draft.text
                    else:
                        batches.setdefault(draft.language, []).append(draft)
                for source_language, group in batches.items():
                    texts = [draft.text for draft in group]
                    result = list(translator.translate(texts, source_language, target))
                    if len(result) != len(texts):
                        raise ValueError(
                            f"translator returned {len(result)} texts for {len(texts)} inputs"
                        )
                    for draft, text in zip(group, result, strict=True):
                        translations[draft.index][target] = text
        finally:
            release(translator)

    segments: list[Segment] = []
    for draft in drafts:
        per_language = translations[draft.index]
        changed = any(text != draft.text for text in per_language.values())
        segments.append(
            Segment(
                id=f"seg-{draft.index:04d}",
                start_s=draft.start_s,
                end_s=draft.end_s,
                speaker=draft.speaker,
                language=draft.language,
                language_confidence=draft.language_confidence,
                text=draft.text,
                translations=dict(per_language),
                translated_from=draft.language if changed else None,
            )
        )

    order: list[str] = []
    for segment in segments:
        if segment.speaker not in order:
            order.append(segment.speaker)
    speakers = [
        SpeakerInfo(
            id=speaker_id,
            name=None,
            voiceprint_match=None,
            speech_s=round(
                sum(s.end_s - s.start_s for s in segments if s.speaker == speaker_id), 3
            ),
            segment_count=sum(1 for s in segments if s.speaker == speaker_id),
        )
        for speaker_id in order
    ]

    warnings: list[str] = []
    if not segments:
        warnings.append(translate("warn.no_speech", lang))

    return Transcript(
        created_at=datetime.now(UTC).replace(microsecond=0),
        source=source,
        config=cfg,
        speakers=speakers,
        segments=segments,
        warnings=warnings,
    )
