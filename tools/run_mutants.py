#!/usr/bin/env python3
"""Handmutanten für das Gauntlet (SPEC Abschnitt 12).

Jeder Mutant baut einen plausiblen Fehler ein. Danach läuft die Testsuite.
Bleibt die Suite grün, hat der Mutant überlebt — dann fehlt ein Test.

Aufruf:  uv run python tools/run_mutants.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutant:
    name: str
    file: str
    old: str
    new: str


MUTANTS: tuple[Mutant, ...] = (
    Mutant(
        "Overlap-Vergleich invertiert",
        "src/transcriber/core.py",
        "if overlap > best_overlap or (overlap == best_overlap and turn_start < best_start):",
        "if overlap < best_overlap:",
    ),
    Mutant(
        "Gleichstand-Regel entfernt (äquivalent, siehe EVIDENCE)",
        "src/transcriber/core.py",
        "if overlap > best_overlap or (overlap == best_overlap and turn_start < best_start):",
        "if overlap > best_overlap:",
    ),
    Mutant(
        "Zielsprache ungeprüft",
        "src/transcriber/core.py",
        "if target not in available:",
        "if False:",
    ),
    Mutant(
        "Übersetzung bei gleicher Sprache überschrieben",
        "src/transcriber/core.py",
        "if draft.language == target:",
        "if False:",
    ),
    Mutant(
        "Sprecher-Zählung falsch",
        "src/transcriber/core.py",
        "segment_count=sum(1 for s in segments if s.speaker == speaker_id),",
        "segment_count=len(segments),",
    ),
    Mutant(
        "SRT-Zeitformat ohne Millisekunden-Trenner",
        "src/transcriber/exporters.py",
        'f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"',
        'f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis // 10:02d}"',
    ),
    Mutant(
        "Warnung bei leerem Transkript entfernt",
        "src/transcriber/core.py",
        'warnings.append(translate("warn.no_speech", lang))',
        "pass",
    ),
    Mutant(
        "Fehlercode der Sprachprüfung auf 1",
        "src/transcriber/errors.py",
        (
            "class UnsupportedLanguageError(TranscriberError):\n"
            '    key = "error.unsupported_language"\n    exit_code = 2'
        ),
        (
            "class UnsupportedLanguageError(TranscriberError):\n"
            '    key = "error.unsupported_language"\n    exit_code = 1'
        ),
    ),
    Mutant(
        "Registry kennt Ports nicht mehr",
        "src/transcriber/registry.py",
        (
            "    def names(self, port: str) -> list[str]:\n"
            "        return sorted(self._factories.get(port, {}))"
        ),
        (
            "    def names(self, port: str) -> list[str]:\n"
            "        return sorted(self._factories.get('x', {}))"
        ),
    ),
    Mutant(
        "Englischer Katalog unvollständig",
        "src/transcriber/i18n/en.json",
        '  "cli.done":',
        '  "cli.done_unused":',
    ),
    Mutant(
        "README-Abschnitt fehlt",
        "README.de.md",
        "## Sprachen",
        "### Sprachen",
    ),
    Mutant(
        "MADLAD-Präfix fehlt",
        "src/transcriber/adapters/mapping.py",
        'return f"<2{code}> {text}"',
        "return text",
    ),
    Mutant(
        "Veraltete Sprachcodes nicht ersetzt",
        "src/transcriber/adapters/mapping.py",
        "return OBSOLETE_CODES.get(code, code)",
        "return code",
    ),
    Mutant(
        "Sprecherwechsel nicht sortiert",
        "src/transcriber/adapters/mapping.py",
        "turns.sort(key=lambda turn: turn.start_s)",
        "pass",
    ),
    Mutant(
        "Leere Whisper-Segmente behalten",
        "src/transcriber/adapters/mapping.py",
        "if not text or end <= start:",
        "if end < start:",
    ),
    Mutant(
        "Adapter wird nicht freigegeben",
        "src/transcriber/core.py",
        "    hook = getattr(adapter, \"release\", None)\n    if callable(hook):\n        hook()",
        "    return None",
    ),
    Mutant(
        "Galerie ohne Zustimmung",
        "src/transcriber/gallery.py",
        "        if not consent:\n            raise GalleryConsentError(name)",
        "        if False:\n            raise GalleryConsentError(name)",
    ),
    Mutant(
        "Galerie-Treffer ohne Schwelle",
        "src/transcriber/gallery.py",
        "            if similarity < self.threshold:",
        "            if False:",
    ),
    Mutant(
        "Löschen lässt Stimmabdrücke stehen (äquivalent: ON DELETE CASCADE)",
        "src/transcriber/gallery.py",
        (
            '                connection.execute('
            '"DELETE FROM voiceprint WHERE person_id = ?", (person_id,))'
        ),
        "                pass",
    ),
    Mutant(
        "Löschen ohne sicheres Überschreiben (äquivalent: VACUUM schreibt neu)",
        "src/transcriber/gallery.py",
        '        connection.execute("PRAGMA secure_delete = ON")',
        "        pass",
    ),
    Mutant(
        "Sperre beim Schreiben entfernt (äquivalent: UNIQUE-Index)",
        "src/transcriber/gallery.py",
        "fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)",
        "pass",
    ),
    Mutant(
        "Untertitel-Filter fehlt",
        "src/transcriber/adapters/video.py",
        '        return f"subtitles={subtitle_file}:force_style=\'{style}\'"',
        '        return "null"',
    ),
    Mutant(
        "Tonspur beim Rendern verworfen",
        "src/transcriber/adapters/video.py",
        '            "-c:a",\n            "copy",',
        '            "-an",',
    ),
    Mutant(
        "Unbekannte Untertitelsprache erlaubt",
        "src/transcriber/adapters/video.py",
        "            if language not in available:",
        "            if False:",
    ),
    Mutant(
        "JSON-Export nicht sortiert",
        "src/transcriber/exporters.py",
        "text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)",
        "text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)",
    ),
)


def main() -> int:
    survivors: list[str] = []
    for mutant in MUTANTS:
        path = ROOT / mutant.file
        original = path.read_text(encoding="utf-8")
        if mutant.old not in original:
            print(f"[FEHLER ] {mutant.name}: Suchtext nicht gefunden")
            survivors.append(mutant.name + " (Suchtext fehlt)")
            continue
        path.write_text(original.replace(mutant.old, mutant.new, 1), encoding="utf-8")
        try:
            run = subprocess.run(
                ["uv", "run", "pytest", "-x", "-q", "--no-header", "-p", "no:randomly"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            path.write_text(original, encoding="utf-8")
        if run.returncode == 0:
            print(f"[ÜBERLEBT] {mutant.name}")
            survivors.append(mutant.name)
        else:
            print(f"[GETÖTET ] {mutant.name}")

    total = len(MUTANTS)
    killed = total - len(survivors)
    print(f"\nErgebnis: {killed}/{total} Mutanten getötet")
    if survivors:
        print("Überlebende:")
        for name in survivors:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
