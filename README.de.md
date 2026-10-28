# Transcriber

Transkription von Audiodateien mit Sprechertrennung, Spracherkennung je Abschnitt, Übersetzung
in eine oder mehrere Zielsprachen, Sprecherwiedererkennung über eine lokale Stimmabdruck-Galerie,
laufendem Ton vom Mikrofon, eingebrannten Untertiteln und einer Weboberfläche.
Jeder Baustein ist ein austauschbares Plug-in.

Stand: **nur P0.** Kern, Datenmodell, Adapter-Registry, Exporte und Kommandozeile sind gebaut und
durch Tests abgedeckt. Die ML-Adapter (faster-whisper, pyannote, VoxLingua107, MADLAD, weSpeaker)
sind **noch nicht angeschlossen** — das ist Stufe P1. Galerie (P2), Streaming (P3), Untertitel im
Video (P4), HTTP-Dienst (P5) und Flet-Oberfläche (P6) sind **nicht gebaut**.

## Was es tut

Ein Lauf macht aus einer Audiodatei ein Transkript. Das Transkript enthält Abschnitte mit Start
und Ende, Sprecherkennung, erkannter Sprache, Originaltext und Übersetzung. Sprecher heißen
`S1`, `S2`, … und bekommen einen Namen, wenn die Galerie sie erkennt.

## Umfang (v1)

| Funktion | Stufe |
|---|---|
| Dateitranskription, Export nach JSON/SRT/VTT/TXT | P0 |
| Adapter für ASR, Diarization, Sprach-ID, Übersetzung | P1 |
| Stimmabdruck-Galerie, Zustimmung, Löschen | P2 |
| Streaming von Mikrofon und stdin | P3 |
| Eingebrannte Untertitel | P4 |
| HTTP-Dienst (FastAPI) | P5 |
| Weboberfläche (Flet) | P6 |

## Installation

```bash
uv sync
```

Python 3.12 ist festgelegt. Das Host-Python 3.14 wird nicht verwendet, weil die ML-Räder auf
3.12 zielen.

## Benutzung

```bash
uv run transcriber transcribe audio.mp3 --target de --out out --format json --format srt
uv run transcriber adapters
uv run transcriber licenses
```

Meldungen sind standardmäßig Deutsch. Mit `--lang en` erscheinen sie in Englisch.

## Konfiguration

```toml
[adapters]
asr = "faster-whisper"
diarizer = "pyannote"
language_id = "voxlingua"
translator = "madlad"
voiceprint = "wespeaker"

[targets]
languages = ["de"]
```

## Adapter und Plug-ins

Der Kern kennt nur Schnittstellen. Ein Adapter wird über seinen Namen in der Konfiguration
gewählt. Ein Plug-in aus einem fremden Paket meldet sich über die Python-Einstiegspunktgruppe
`transcriber.adapters` an; jeder Einstiegspunkt ist eine Funktion, die die Registry bekommt.
Eine Änderung am Kern ist nicht nötig.

## Ausgabeformat

```json
{
  "schema_version": 1,
  "mode": "file",
  "source": {"path": "...", "sha256": "...", "duration_s": 2.0,
             "sample_rate_hz": 16000, "channels": 1},
  "config": {"asr": "fake", "diarizer": "fake", "language_id": "fake",
             "translator": "fake", "voiceprint": null, "target_languages": ["de"]},
  "speakers": [{"id": "S1", "name": null, "voiceprint_match": null,
                "speech_s": 1.0, "segment_count": 1}],
  "segments": [{"id": "seg-0001", "start_s": 0.0, "end_s": 1.0, "speaker": "S1",
                "language": "de", "language_confidence": 0.9, "text": "Hallo Welt",
                "translations": {"de": "Hallo Welt"}, "translated_from": null,
                "is_final": true}],
  "warnings": []
}
```

## Sprachen

Die Doku gibt es in Englisch (`README.md`) und Deutsch (`README.de.md`) mit denselben
Abschnitten. Meldungen und Oberfläche lassen sich zwischen Deutsch und Englisch umschalten;
Standard ist Deutsch. Technische Kennungen (`S1`, `job_id`, Feldnamen, Exit-Codes) werden nie
übersetzt.

## Lizenzen

Alle vorgesehenen Modelle und Bibliotheken sind kommerziell nutzbar: MIT, Apache-2.0, BSD-3 und
ein Modell unter CC-BY-4.0 mit Namensnennung. NLLB-200 wurde abgelehnt, weil es CC-BY-NC-4.0 ist.
Die Tabelle mit Prüfdatum steht in `LICENSES.md`, die Namensnennung in `NOTICE`.

Der ffmpeg-Build auf diesem Host ist ein GPL-Build (`--enable-gpl`). Die eigene Nutzung ist
unproblematisch. Wer das Produkt mit diesem Build weitergibt, löst GPL-Pflichten aus; für die
Weitergabe ist ein LGPL-Build einzuplanen.

## Tests und Qualität

```bash
uv run pytest
uv run mypy
uv run ruff check
```

Die Abnahmekriterien stehen in `SPEC.md`, Abschnitt 5. Jedes Kriterium gehört zu genau einem Test.

## Stand

Stufe P0 ist fertig. Die nächste Stufe P1 braucht die gated pyannote-Modelle; der Zugang ist
freigegeben und mit einem echten Download geprüft.
