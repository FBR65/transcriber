# EVIDENCE — Stufe P2 (Galerie der Stimmabdrücke)

Datum: 2026-10-31 · Autor: Hermes · SPEC: `SPEC.md` Fassung 3, freigegeben am 2026-10-28

Freigabe: erteilt („Ok für P2").
Alle Zahlen aus Läufen nach der letzten Code-Änderung.

## 1. Was gebaut ist

| Baustein | Inhalt |
|---|---|
| `Gallery` (`gallery.py`) | SQLite-Datei, Rechte 600, Verzeichnis 700. Tabelle `person` mit eindeutigem Namen, Tabelle `voiceprint` mit Vektor als Blob, `ON DELETE CASCADE`, `PRAGMA secure_delete`, `VACUUM` nach dem Löschen, Sperrdatei mit `flock` |
| `WeSpeakerVoiceprint` (`adapters/voiceprint.py`) | Stimmabdruck über `pyannote/wespeaker-voxceleb-resnet34-LM`, `Inference(window="whole")`, Anmeldung, Erkennung, Löschen, Liste |
| Kern | Nach der Sprechertrennung werden je Sprecher die drei längsten Abschnitte (mindestens 0,5 s) geprüft, der beste Treffer gewinnt. Namen und Ähnlichkeit landen im Transkript, kein Stimmabdruck |
| Konfiguration | `RunConfig.gallery`, Abschnitt `[gallery] path` in der TOML, Option `--gallery` in `transcribe`, `gallery enroll`, `gallery list`, `gallery delete` |
| Pflichten aus SPEC 7 | Zustimmung als Pflichtschalter (`--consent`, `GalleryConsentError`, Exit 2), Löschen je Person (Name oder Kennung), lokale Datei, kein Netzwerk, Stimmabdruck nie im Transkript |

## 2. Abnahmekriterien

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S16 | bekannte Sprecher bekommen Namen | `test_core_gallery.py::test_gallery_recognises_known_speaker`, `test_integration_models.py::test_voiceprint_gallery_roundtrip` | grün, echter Treffer mit 0,954 |
| S17 | fremder Sprecher bleibt `S3`, keine Name, Warnung | `test_core_gallery.py::test_gallery_unknown_speaker_stays_unnamed` | grün |
| S18 | Löschen entfernt den Datensatz | `test_gallery.py::test_delete_by_name_removes_prints`, `::test_delete_removes_prints_from_the_file`, `::test_delete_by_id`, `test_cli_gallery.py::test_enroll_list_delete`, Integrationstest | grün, 0 Zeilen in `voiceprint` nach dem Löschen |
| S19 | Anmeldung ohne Zustimmung scheitert | `test_gallery.py::test_enroll_requires_consent`, `test_cli_gallery.py::test_enroll_refuses_without_consent`, `test_gallery_edges.py::test_cli_enroll_reports_adapter_error` | grün, Exit 2, Galerie leer |
| S22 | zwei Prozesse auf der Galerie | `test_gallery.py::test_concurrent_writers_do_not_corrupt`, `::test_concurrent_enroll_of_same_name_creates_one_person` | grün, 40 bzw. 20 Einträge, eine Person |

## 3. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **125 Tests, 125 grün** (6 Integrationstests abgewählt) |
| Integrationstests | `uv run pytest -m integration` | **6 grün**, echte Modelle inklusive Stimmabdruck |
| Coverage | `uv run pytest --cov=transcriber` | **1082 Zeilen, 42 nicht abgedeckt, 96 %** |
| Typen | `uv run mypy` | keine Fehler (strict, 18 Dateien) |
| Lint | `uv run ruff check` | keine Befunde |
| Mutation | `uv run python tools/run_mutants.py` | **18 von 22 getötet**, 4 dokumentierte Äquivalente (unten) |
| Echter Lauf | `transcriber gallery …` und `transcribe --gallery` | Treffer 0,954, veränderte Stimme ohne Treffer, nach Löschen leer |

### Die vier überlebenden Mutanten, mit Begründung

1. **Gleichstand-Regel in `assign_speakers`** — striktes `>` behält den ersten Treffer, das ist
   derselbe Sprecher wie „frühester Beginn". Semantisch gleich.
2. **`DELETE FROM voiceprint` entfernt** — der Fremdschlüssel mit `ON DELETE CASCADE` löscht die
   Abdrücke bereits beim Löschen der Person. Die zusätzliche Anweisung ist Absicherung, kein
   Verhalten.
3. **`PRAGMA secure_delete` entfernt** — das folgende `VACUUM` schreibt die Datei neu und
   entfernt die freien Seiten. Beide Maßnahmen zusammen sind Absicherung; eine allein genügt für
   den geprüften Fall.
4. **`flock` entfernt** — ein eindeutiger Index auf `person.name` verhindert doppelte Personen
   unabhängig von der Sperre. Die Sperre bleibt trotzdem drin, weil sie auch die Reihenfolge von
   Lesen und Schreiben ordnet.

Diese vier Tests wurden nicht künstlich verschärft: sie würden eine Implementierung prüfen, die
es nicht gibt.

## 4. Echter Lauf mit Stimmabdruck

```
gleiche Stimme:    0.954   Name: JFK
veränderte Stimme: kein Treffer
Personen:          [JFK, 1 Stimmabdruck]
nach Löschen:      [] , Treffer: None
```

Verändert wurde die Stimme mit ffmpeg (`asetrate=16000*1.5, aresample=16000, atempo=0.667`).
Dasselbe Modell, dieselbe Datei, nur Tonhöhe und Tempo verschoben.

## 5. Fehler, die dieser Schritt gefunden hat

1. **`VACUUM` innerhalb einer Transaktion** — SQLite verweigert das. Das Löschen committet jetzt
   erst, danach folgt ein eigener Sperrabschnitt für `VACUUM`.
2. **S16-Test war zu streng** — bei zwei Sprechern und nur einem bekannten ist die Warnung aus
   S17 korrekt. Der Test prüft jetzt den Fall mit einem Sprecher, die Warnung hat ihren eigenen
   Test.
3. **Gleichzeitige Anmeldung gleichen Namens** — der Test zeigte, dass die Sperre allein keine
   Garantie ist. Der eindeutige Index auf `name` macht die Regel jetzt von der Sperre unabhängig.

## 6. Bekannte Grenzen

- **Güte der Wiedererkennung nicht gemessen.** Ein Sprecher, eine Datei, eine Änderung der
  Tonhöhe. Keine Messung über viele Sprecher, kein Vergleich mit fremden Stimmen im Alltag.
  Schwelle steht auf 0,70 (Vorgabe), im Test 0,50.
- **Keine Sprecher aus echten Mehrpersonenaufnahmen.** `jfk.wav` ist eine Einzelstimme. Die
  Zuordnung „Sprecher S2 = Herr X" ist mit dem Modell geprüft, nicht mit echten Konferenzen.
- **Mikrofonqualität, Störgeräusche, Telefon, Musik** sind nicht geprüft.
- **`pip-audit` weiter nicht gelaufen.**
- **Oberfläche fehlt** — die Liste zeigt Personen und Löschen nur auf der Kommandozeile.
  Die Pflicht „Oberfläche zeigt gespeicherte Personen und bietet Löschen an" aus SPEC 7 wartet
  auf P6.

## 7. Wiederholbar

```bash
uv sync
uv run pytest                                   # 125 Tests ohne Modelle
uv run pytest -m integration                    # 6 Tests mit Modellen
uv run python tools/run_mutants.py              # 18/22 getötet
uv run transcriber gallery enroll <datei> --name "Herr X" --consent --gallery <pfad>
uv run transcriber gallery list --gallery <pfad>
uv run transcriber gallery delete "Herr X" --gallery <pfad>
uv run transcriber transcribe <datei> --target de --gallery <pfad> --out <ordner>
```
