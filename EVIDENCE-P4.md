# EVIDENCE — Stufe P4 (Untertitel im Video)

Datum: 2026-10-31 · Autor: Hermes · SPEC: `SPEC.md` Fassung 3

Freigabe: erteilt („P4 und dann einen Test mit einem Youtube Video mit mehreren stimmen").
Alle Zahlen aus Läufen nach der letzten Code-Änderung.

## 1. Was gebaut ist

| Baustein | Inhalt |
|---|---|
| Port `VideoRenderer` | `render(video, transcript, out, language=None) -> Path` |
| `FfmpegVideoRenderer` (`adapters/video.py`) | schreibt die SRT in einen Arbeitsordner, brennt sie mit dem libass-Filter ein, `libx264`, `-crf 20`, `-preset veryfast`, Tonspur wird kopiert, `+faststart` |
| Sprache der Untertitel | `--subtitle-lang de` wählt den Text aus `translations`; ohne Angabe nimmt `_spoken()` die erste Übersetzung |
| Befehl | `transcriber render VIDEO --transcript JSON --out MP4 [--subtitle-lang de]` |
| Fehler | `VideoRenderError` für fehlende Datei, leeres Transkript, unbekannte Untertitelsprache, ffmpeg-Fehler, leere Ausgabe |
| Zusätzlich nötig | `audio.to_mono_wav()`: mp4 und Mehrkanal werden vor dem Lauf nach mono-WAV gewandelt (siehe Abschnitt 4) |

## 2. Abnahmekriterium S20

| Prüfung | Test | Ergebnis |
|---|---|---|
| Bild- und Tonstrom vorhanden | `test_video.py::test_burned_in_subtitles`, `::test_audio_stream_is_kept` | grün |
| Laufzeit ±0,1 s zur Quelle | `test_video.py::test_burned_in_subtitles` | grün, 3,0 s gegen 3,0 s |
| Untertitelbereich weicht vom Quellbild ab | `test_video.py::test_burned_in_subtitles` (Pixelvergleich unten gegen oben) | grün, Abweichung unten mehr als doppelt so groß wie oben |
| Filteraufbau | `test_video.py::test_command_contains_libass_filter` | grün |

## 3. Sichtprüfung am echten Ergebnis

Quelle: 640×360, 11 s, `testsrc2`-Testbild mit dem Ton von `jfk.wav`. Lauf über die CLI mit
allen echten Modellen: 24,0 s, danach `transcriber render` → 747 KB MP4, 11,000 s, Video und
Audio vorhanden.

Ein Bild bei Sekunde 5 aus dem unteren Drittel zeigt den eingebrannten Untertitel:

> [S1] Und so, meine amerikanischen Mitbürger, fragen Sie nicht, was Ihr Land für Sie tun kann,
> fragen Sie, was Sie für Ihr Land tun können.

Das ist derselbe Text wie im Transkript, also kein Platzhalter und keine Attrappe.

## 4. Fehler, die dieser Schritt gefunden hat

**mp4 ließ den Lauf scheitern.** `LibsndfileError: Format not recognised` — pyannote liest Ton
über torchaudio, und torchaudio fällt bei mp4 auf soundfile zurück, das mp4 nicht kennt.
Behoben in `audio.to_mono_wav()`: alles, was kein mono-16-kHz-WAV ist, wird vor dem Lauf mit
ffmpeg gewandelt und danach gelöscht. Damit arbeiten ASR, Diarization und Sprach-ID auf einem
Format, das alle drei lesen.

Zweiter Befund: das Testvideo ohne Sprache (nur 440-Hz-Ton) ergibt ein leeres Transkript, und
`render` verweigert das korrekt mit `VideoRenderError`. Für den echten Lauf wurde deshalb ein
Video mit dem Ton von `jfk.wav` gebaut.

## 5. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **131 Tests, 131 grün** (6 Integrationstests abgewählt) |
| Coverage | `uv run pytest --cov=transcriber` | **1177 Zeilen, 64 nicht abgedeckt, 95 %** |
| Typen | `uv run mypy` | keine Fehler (strict, 19 Dateien) |
| Lint | `uv run ruff check` | keine Befunde |
| Mutation | `uv run python tools/run_mutants.py` | **21 von 25 getötet**, 4 dokumentierte Äquivalente (siehe EVIDENCE-P0/P2) |
| Echter Lauf | `transcribe` + `render` auf MP4 | Exit 0, 24,0 s, Bild geprüft |

Neue Mutanten in dieser Stufe: Filter entfernt, Tonspur verworfen, unbekannte Untertitelsprache
erlaubt. Alle drei getötet.

## 6. Bekannte Grenzen

- **Nur ein Testvideo.** 640×360, 11 s, ein Sprecher, künstliches Testbild. Kein echtes
  Filmmaterial, keine Sprecherüberlappung, keine Schriftwahl für fremde Zeichensätze.
- **Harte Untertitel, keine Positionierung pro Sprecher.** Alle Sprecher landen unten mittig.
  Zwei Sprecher gleichzeitig werden nicht getrennt dargestellt.
- **Neu kodiert.** Das Bild wird neu komprimiert (`libx264`, CRF 20). Ein Vergleich der
  Bildqualität zur Quelle wurde nicht gemessen.
- **`pip-audit` weiter nicht gelaufen.**

## 7. Wiederholbar

```bash
uv sync
uv run pytest                                   # 131 Tests
uv run transcriber transcribe video.mp4 --target de --out out --format json
uv run transcriber render video.mp4 --transcript out/video.json --out out/untertitelt.mp4 \
    --subtitle-lang de
```

Test mit einem YouTube-Video: `tools/youtube_test.py` lädt mit yt-dlp, transkribiert, exportiert
und brennt die Untertitel ein. Aufruf:

```bash
uv run python tools/youtube_test.py <URL> --target de --out out-youtube
```
