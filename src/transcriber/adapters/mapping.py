"""Reine Umrechnungen. Ohne Modelle testbar, deshalb getrennt von den Adaptern."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..ports import AsrSegment, SpeakerTurn

# VoxLingua107 benutzt teils veraltete ISO-Codes. Die Modellkarte nennt zwei bekannte Fälle.
OBSOLETE_CODES = {"iw": "he", "jw": "jv", "in": "id", "ji": "yi"}

# Sprachen, für die MADLAD-400 trainiert ist (Auswahl der häufigsten Codes).
# Nicht vollständig: das Modell kennt über 400 Sprachen. Unbekannte Codes werden abgelehnt.
MADLAD_LANGUAGES = frozenset(
    """
    af am ar as az be bg bn bs ca cs cy da de el en eo es et eu fa fi fr ga gl gu he hi hr hu
    hy id is it ja jv ka kk km kn ko ku ky la lb lo lt lv mk ml mn mr ms mt my ne nl no or pa
    pl ps pt ro ru si sk sl sq sr sv sw ta te th tl tr uk ur uz vi yi zh
    """.split()
)


def language_code(label: str) -> str:
    """„en: English“ → „en“. Veraltete Codes werden ersetzt."""
    code = label.split(":", 1)[0].strip().lower()
    return OBSOLETE_CODES.get(code, code)


def madlad_prompt(target: str, text: str) -> str:
    """MADLAD erwartet den Zielsprachencode als Präfix."""
    code = target.strip().lower()
    if not code:
        raise ValueError("empty target language")
    return f"<2{code}> {text}"


def segments_from_whisper(items: Iterable[object], language: str | None = None) -> list[AsrSegment]:
    """Wandelt Whisper-Segmente um. Leere Texte fallen weg."""
    result: list[AsrSegment] = []
    for item in items:
        start = float(item.start)  # type: ignore[attr-defined]
        end = float(item.end)  # type: ignore[attr-defined]
        text = str(item.text).strip()  # type: ignore[attr-defined]
        if not text or end <= start:
            continue
        result.append(AsrSegment(start_s=start, end_s=end, text=text, language=language))
    return result


def turns_from_annotation(raw: Iterable[tuple[float, float, str]]) -> list[SpeakerTurn]:
    """Wandelt (Start, Ende, Kennung) in Sprecherwechsel um und wirft leere Abschnitte weg."""
    turns: list[SpeakerTurn] = []
    for start, end, label in raw:
        if end <= start:
            continue
        turns.append(SpeakerTurn(start_s=float(start), end_s=float(end), speaker=str(label)))
    turns.sort(key=lambda turn: turn.start_s)
    return turns


def madlad_languages() -> set[str]:
    return set(MADLAD_LANGUAGES)


def is_supported_target(target: str) -> bool:
    return target.strip().lower() in MADLAD_LANGUAGES


def language_list_text() -> Sequence[str]:
    return sorted(MADLAD_LANGUAGES)
