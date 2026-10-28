# EVIDENCE — Stufe P0 (Gerüst)

Datum: 2026-10-28 · Autor: Hermes · SPEC: `SPEC.md` Fassung 3, freigegeben am 2026-10-28
Quellstand: Commit `HEAD` nach diesem Bericht (siehe `git log -1`)

Freigabe des SPEC: **erteilt** („Freigabe" am 2026-10-28). Alle Zahlen unten stammen aus einem
Abschlusslauf nach der letzten Code-Änderung.

## 1. Umfang dieser Stufe

Gebaut: Datenmodell, Adapter-Registry mit Einstiegspunkten, Konfiguration, Kern (Dateimodus),
Tonprüfung über ffprobe, Exporte (json, srt, vtt, txt), Kommandozeile, Meldungen DE/EN,
Lizenzwächter, Beispiel-Plug-in, Doku.

Nicht gebaut (P1–P6): ML-Adapter, Galerie, Streaming, Untertitel im Video, HTTP-Dienst,
Flet-Oberfläche. Für diese Punkte gibt es **keine** Tests, weil es keinen Code gibt.

## 2. SPEC-Kriterien → Test → Ergebnis

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S1 | ein Sprecher, Ziel = Quellsprache | `test_core.py::test_single_speaker_same_language` | grün (Kern mit Test-Adaptern) |
| S2 | zwei Sprecher | `test_core.py::test_two_speakers_assigned`, `test_mutation_gaps.py::test_speaker_counts_and_speech_time` | grün |
| S3 | zwei Sprachen, dritte Zielsprache | `test_core.py::test_multilingual_translation` | grün |
| S4 | Zielsprache unbekannt, Exit 2 | `test_core.py::test_unsupported_target_language` | grün |
| S5 | Adapter unbekannt, Liste der Namen | `test_core.py::test_unknown_adapter_name` | grün |
| S6 | Adapter-Tausch per Konfiguration | `test_core.py::test_adapter_swap_translator` | grün |
| S7 | Export in vier Formaten | `test_export.py::test_export_formats` | grün |
| S8 | API und CLI gleich | `test_cli.py::test_api_cli_parity` | grün |
| S9 | beschädigte Datei, Exit 1, keine Ausgabe | `test_cli.py::test_corrupt_audio` | grün |
| S10 | stille Datei, Warnung | `test_cli.py::test_silent_audio` | grün |
| S11 | zwei Läufe gleich | `test_core.py::test_deterministic_output` | grün |
| S12 | Zuordnung nach größter Überschneidung | `test_core.py::test_overlap_assignment_rule`, `test_mutation_gaps.py::test_assign_speakers_tie_goes_to_earliest_start` | grün |
| S15 | Ordner, ein Fehler je Datei, kein Abbruch | `test_folder.py::test_folder_partial_failure` | grün |
| S27 | Sprachkataloge vollständig, gleiche Platzhalter | `test_i18n_docs.py::test_i18n_keys_complete`, `::test_i18n_placeholders_are_filled` | grün |
| S28 | `--lang en` wirkt, Kennungen bleiben | `test_cli.py::test_cli_language_switch` | grün |
| S30 | beide READMEs, gleiche Abschnitte | `test_i18n_docs.py::test_docs_bilingual_parity`, `test_mutation_gaps.py::test_docs_heading_levels_match` | grün |
| S31 | keine NC-Lizenz in der Standardkonfiguration | `test_licensing.py::test_default_adapters_have_commercial_licences` | grün |
| S13, S14 | Streaming | — | **nicht gebaut (P3)** |
| S16–S19, S22 | Galerie | — | **nicht gebaut (P2)** |
| S20 | Untertitel im Video | — | **nicht gebaut (P4)** |
| S21 | Oberfläche | — | **nicht gebaut (P6)** |
| S23–S26 | HTTP-Dienst | — | **nicht gebaut (P5)** |

Wichtig: S1–S3 prüfen die **Kernlogik** mit Test-Adaptern. Sie prüfen nicht die Qualität von
Whisper, pyannote, VoxLingua oder MADLAD. Diese Qualität wird in P1 auf echter Sprache gemessen.

## 3. Gauntlet, Schicht für Schicht

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **71 Tests, 71 grün**, 1,15 s |
| Coverage | `uv run pytest --cov=transcriber --cov-report=term-missing` | **568 Zeilen, 1 nicht abgedeckt, 99 %**. Offene Zeile: `core.py:110` (Schutz gegen falsche Rückgabezahl des Übersetzers) |
| Typen | `uv run mypy` | **Success: no issues found in 12 source files** (strict) |
| Lint | `uv run ruff check` | **All checks passed** |
| Mutation (Handmutanten) | `uv run python tools/run_mutants.py` | **11 von 12 getötet**. Der Überlebende ist äquivalent, Begründung unten |
| Zufällige Reihenfolge | `uv run pytest --randomly-seed={1,42,4711,99,2026}` | **5 von 5 grün** |
| Echter Lauf | `uv run transcriber transcribe /tmp/tc-real/echt.mp3 …` | Exit 0, siehe Abschnitt 4 |
| Property-Tests | `tests/test_properties.py` | 200 zufällige Transkripte Modell-Rundreise, 300 Sprecher-Zuordnungen |
| Abhängigkeiten | nicht geprüft | **übersprungen:** kein `pip-audit` im Setup-Plan. Die Abhängigkeiten sind auf die im SPEC genehmigten Pakete beschränkt; die Lizenzen sind im Test `test_licensing.py` geprüft |

### Der überlebende Mutant

„Gleichstand-Regel entfernt": Die Bedingung
`overlap > best_overlap or (overlap == best_overlap and turn_start < best_start)` wird zu
`overlap > best_overlap`. Mit striktem `>` bleibt bei Gleichstand der **erste** gefundene
Sprecher stehen — und die Schleife läuft in Zeitreihenfolge. Damit ist das Verhalten identisch:
im Gleichstand gewinnt der früheste Beginn. Der Mutant ist semantisch äquivalent und nicht
tötbar. Er bleibt als dokumentierter Überlebender stehen, statt einen sinnlosen Test zu bauen.

Gefunden wurde er trotzdem nützlich: der erste Anlauf der Mutantenprüfung zeigte 5 Überlebende.
Drei davon waren echte Testlücken (Zuordnung bei Gleichstand, `segment_count`, stabiler
JSON-Export), eine war die Doku-Prüfung (nur Anzahl statt Ebenen der Überschriften). Alle vier
Tests sind nachgezogen; sie stehen in `tests/test_mutation_gaps.py`.

## 4. Echter Lauf (kein Testrahmen)

Beispiel-Plug-in installiert mit `uv pip install -e examples/demo-plugin`. Die Adapter kommen
über den Einstiegspunkt `transcriber.adapters`, ohne Änderung am Kern.

```
$ uv run transcriber adapters
Registrierte Adapter:
  asr: demo
  diarizer: demo
  language_id: demo
  translator: demo

$ uv run transcriber transcribe /tmp/tc-real/echt.mp3 /tmp/tc-real/sechs-kanal.wav \
    --config /tmp/tc-real/demo.toml --out /tmp/tc-real/out \
    --format json --format srt --format vtt --format txt
Geschrieben: /tmp/tc-real/out/echt.json
...
Fertig: 3 Segmente, 2 Sprecher, 2 Sprachen.
EXIT=0
```

Geprüft am Ergebnis:

- `echt.mp3`: 44 100 Hz, 1 Kanal, 3,00 s — ffprobe liest echte Werte.
- `sechs-kanal.wav`: 44 100 Hz, **6 Kanäle**, 2,00 s — Mehrkanal wird angenommen.
- Sprecher `SPEAKER_00`/`SPEAKER_01` des Adapters werden zu **S1/S2** normalisiert.
- Segment 2 ist englisch, Ziel ist Englisch: `translated_from` ist `null`, Übersetzung = Text.
- Segmente 1 und 3 sind deutsch: `translated_from = "de"`, Übersetzung gesetzt.
- SRT: `00:00:00,000 --> 00:00:01,200`, Sprecherkennung `[S1]`.
- VTT beginnt mit `WEBVTT`.
- TXT enthält Originaltext und die Übersetzung in der zweiten Zeile.

## 5. Fehler, die das Gauntlet gefunden hat

1. **Reihenfolgeabhängige Tests.** Nach der Installation des Beispiel-Plug-ins schlugen zwei
   Tests fehl, weil sie eine leere Registry erwarteten. Ursache: `discover()` findet jetzt den
   Einstiegspunkt. Behoben in den Tests, nicht im Produkt: die Tests prüfen jetzt „Name nicht in
   der Liste" statt „Liste ist leer".
2. **Fünf Mutanten überlebten** den ersten Lauf. Vier echte Testlücken, ein äquivalenter Mutant
   (Abschnitt 3).
3. **`translate()` ließ fehlende Platzhalter stehen.** `"Fertig: {segments} …"` wäre mit leerem
   Text ausgegeben worden. Jetzt formatiert `translate()` immer und wirft bei fehlendem
   Platzhalter. Der Test `test_missing_placeholder_raises` deckt das ab.
4. **Testfehler mit falscher Erwartung.** `test_adapter_swap_translator` erwartete eine
   Übersetzung auch für die Zielsprache selbst. SPEC S1 sagt das Gegenteil. Der Test wurde an
   den SPEC angepasst, nicht der Code.

## 6. Bekannte Grenzen dieser Stufe

- **Keine ML-Qualität geprüft.** Ohne Modelle gibt es keine Aussage zu Wortfehlerrate,
  Sprechergüte oder Übersetzungsqualität.
- **3-Stunden-Datei nicht getestet.** Der adversarische Durchgang aus SPEC Abschnitt 12 enthält
  diesen Punkt; er braucht einen Lauf mit Modellen (P1), weil Speicher und Laufzeit erst dort
  entstehen.
- **Eine Codezeile ohne Test:** `core.py:110`, Schutz gegen eine falsche Rückgabezahl des
  Übersetzers. Der Schutz ist mit `test_branches.py::test_translator_with_wrong_count_is_rejected`
  von der anderen Seite geprüft (Fehler kommt an); die Zeile selbst wird nicht ausgeführt.
- **`pip-audit` fehlt.** Kein Schwachstellen-Scan der Abhängigkeiten in diesem Lauf.
- **ffmpeg ist ein GPL-Build.** Gilt weiter, siehe `README.md` und `SPEC.md` Abschnitt 6.

## 7. Wiederholbar

```bash
uv sync
uv run pytest --cov=transcriber --cov-report=term-missing
uv run mypy
uv run ruff check
uv run pytest --randomly-seed=42
uv run python tools/run_mutants.py
uv pip install -e examples/demo-plugin
uv run transcriber transcribe <datei> --config <demo.toml> --out <ordner> --format json
```

Versionen: Python 3.12.14, pytest 8.x, ruff 0.17.3, mypy 1.x, pydantic 2.x, typer 0.27.3,
ffmpeg/ffprobe 9.0.1. Genaue Stände in `uv.lock`.
