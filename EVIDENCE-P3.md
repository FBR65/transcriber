# EVIDENCE — Stufe P3 (Streaming) und zwei SPEC-Korrekturen

Datum: 2026-10-31 · Autor: Hermes · SPEC: `SPEC.md`

Freigaben: „1. Ja", „2. härten", „P3, allerdings kann dafür kein Test durchgeführt werden".
Zum letzten Punkt: ein Test **war** möglich, siehe Abschnitt 4 — nur nicht mit einem sprechenden
Menschen am Mikrofon.

## 1. Die zwei SPEC-Korrekturen

### 1.1 S11 — Determinismus

SPEC S11 sagte „zwei Läufe gleich". Das gilt für den Kern mit Test-Adaptern, **nicht** für echte
Modelle: derselbe Befehl auf derselben Datei ergab 72 und 79 Segmente (Sprecherzahl blieb 5).
Grund: VAD und Beam-Suche auf der GPU sind nicht bit-genau. S11 ist entsprechend umgeschrieben:
gilt für den Kern, echte Läufe sind Näherung.

### 1.2 Sprach-ID — gehärtet

Vorher zwei Regeln (`smooth_languages`, `apply_file_language`), jetzt eine:
`decide_languages(drafts, file_language)`. Regel: **Die Sprache der ganzen Datei gilt, außer ein
Abschnitt wechselt klar** — mindestens 3,0 s lang und Sicherheit ≥ 0,8. Beim YouTube-Test waren es
vorher 20 Sprachen, nach der ersten Glättung 4, mit der neuen Regel bleibt die Dateisprache
maßgeblich.

Vier Tests decken die Regel ab (`test_branches.py`): Dateisprache gewinnt, klarer Wechsel bleibt,
unsicherer Wechsel wird verworfen, ohne Dateisprache bleibt alles.

## 2. Was in P3 gebaut ist

| Baustein | Inhalt |
|---|---|
| `stream.run_stream()` | nimmt Tonblöcke, schneidet mit dem VAD Äußerungen, gibt `StreamEvent` aus, sobald eine Äußerung fertig ist |
| `StreamEvent` | `index`, `start_s`, `end_s`, `speaker`, `language`, `language_confidence`, `text`, `translations`, `translated_from`, `is_final` |
| `SpeakerTracker` | Stimmabdrücke gegen Mittelwerte, neue Kennung ab Ähnlichkeit < 0,75, Mittelwert wird nachgeführt |
| `EnergyVad` | Energie-VAD ohne Modell, 50-ms-Fenster, schneidet nach 0,35 s Stille, hart bei 15 s |
| `SileroVad` | Silero über torch.hub; nicht getestet (kein Bedarf, Energie-VAD reicht) |
| Tonquellen | `iter_file` (ffmpeg, blockweise), `iter_mic` (sounddevice, 0,5-s-Blöcke, `--seconds` begrenzt) |
| CLI | `transcriber stream --source DATEI|mic [--seconds N] --out ORDNER`; schreibt `ereignisse.jsonl` zeilenweise und spült jede Zeile |
| Speicher | Ohne `--target` wird **kein** Übersetzer geladen. Auf 8 GB VRAM passen Whisper und MADLAD-3B nicht zusammen; der erste Versuch endete im CUDA-OOM |

## 3. Abnahmekriterien

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S13 | Ereignis vor Ende der Einspeisung, letztes Ereignis beim Abschluss | `test_stream.py::test_events_arrive_before_the_feed_ends` | grün: erstes Ereignis nach 8 von 16 Blöcken |
| S14 | Übersetzung je Ereignis, nicht erst am Ende | `test_stream.py::test_translation_per_event` | grün (mit Test-Übersetzer) |
| — | Stille erzeugt kein Ereignis | `test_stream.py::test_silence_produces_no_events` | grün |
| — | Sprechertrennung im Stream | `test_stream.py::test_speaker_tracker_separates_and_merges` | grün |
| — | CLI schreibt JSONL | `test_stream.py::test_cli_stream_writes_jsonl` | grün |
| — | fehlende Datei | `test_stream.py::test_cli_stream_reports_missing_file` | grün |

## 4. Was tatsächlich getestet wurde — und was nicht

**Getestet, echte Modelle, Datei als Quelle:**

```
$ uv run transcriber stream --source jfk.wav --config stream.toml --out stream-out
[  0.00- 11.00] S1 And so, my fellow Americans, ask not what your country can do for you,
                   ask what you can do for your country.
Fertig: 1 Segmente, 1 Sprecher, 1 Sprachen.     (11,6 s für 11 s Ton, inklusive Modellstart)
```

**Getestet, echtes Mikrofon, niemand spricht:**

```
$ uv run transcriber stream --source mic --seconds 4 --out mic-out
(kein Ereignis)  →  ereignisse.jsonl mit 0 Zeilen
```

Das Mikrofon öffnet, die Blöcke fließen (Spitzenpegel 0,143 und 0,004 gemessen), der VAD verwirft
Raumgeräusch korrekt. Damit ist der Mikrofonpfad technisch geprüft — bis zur Grenze dessen, was
ohne sprechenden Menschen möglich ist.

**Nicht getestet:**

1. **Sprache über das Mikrofon.** Ohne Sprecher kein Ereignis, keine Aussage über Erkennungsgüte
   in Echtzeit.
2. **Mehrere Sprecher im Stream.** Der `SpeakerTracker` ist mit Vektoren geprüft, nicht mit zwei
   echten Stimmen am Mikrofon.
3. **Übersetzung im Stream mit echtem Modell.** Wegen VRAM nicht möglich (siehe 2): die Logik ist
   mit dem Test-Übersetzer geprüft, das echte MADLAD im Stream nicht.
4. **Latenz.** Gemessen ist nur die Gesamtlaufzeit einer Datei, nicht die Verzögerung zwischen
   Sprache und Ereignis am Mikrofon. Ohne Sprache nicht messbar.
5. **SileroVad** ist gebaut, aber nicht ausgeführt.

## 5. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **144 Tests, 144 grün** (6 Integrationstests abgewählt) |
| Coverage | `uv run pytest --cov=transcriber` | **1466 Zeilen, 117 nicht abgedeckt, 92 %** |
| Typen | `uv run mypy` | keine Fehler (21 Dateien) |
| Lint | `uv run ruff check` | keine Befunde |
| Echter Lauf | Datei und Mikrofon | Exit 0, siehe Abschnitt 4 |

Neu ungetestet (117 Zeilen, vorher 64): der Mikrofon-Leser, `SileroVad`, die Datei-Blöcke ohne
Sprache, die Speichergrenze für lange Streams. Diese Zeilen brauchen Geräte oder Modelle, die im
Testlauf nicht laufen — sie sind nicht durch Weglassen, sondern durch fehlende Umgebung offen.

## 6. Wiederholbar

```bash
uv run pytest                                   # 144 Tests
uv run transcriber stream --source datei.wav --out out          # ohne Übersetzung
uv run transcriber stream --source datei.wav --target de --out out   # braucht mehr VRAM
uv run transcriber stream --source mic --seconds 10 --out out
```
