# EVIDENCE — Stufe P1 (echte Modelle)

Datum: 2026-10-28 · Autor: Hermes · SPEC: `SPEC.md` Fassung 3, freigegeben am 2026-10-28

Freigabe: erteilt („Freigabe" am 2026-10-28, danach „Freigabe" für P1).
Alle Zahlen aus Läufen nach der letzten Code-Änderung.

## 1. Was gebaut ist

| Baustein | Inhalt |
|---|---|
| `WhisperAsr` | faster-whisper large-v3, int8_float16 auf CUDA, VAD an, Sprache je Abschnitt absichtlich leer (das macht der Sprach-ID-Adapter) |
| `PyannoteDiarizer` | pyannote.audio 3.4 mit Pipeline `pyannote/speaker-diarization-3.1` |
| `VoxLinguaLanguageId` | speechbrain ECAPA auf VoxLingua107, Ton über PyAV dekodiert, Datei je Lauf einmal geladen |
| `MadladTranslator` | MADLAD-400-3B-MT über transformers, bf16, `device_map` lädt Gewicht für Gewicht auf die GPU |
| Anmeldung | eigener Einstiegspunkt `builtin = transcriber.adapters.builtin:register` |
| Kern | Adapter werden je Stufe erzeugt und danach freigegeben (`release()`), damit nie alle Modelle gleichzeitig im Speicher liegen |
| Sprach-ID | läuft nur, wenn ein ASR-Abschnitt keine Sprache mitbringt |

## 2. Abnahmekriterien

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S1 | ein Sprecher, Ziel = Quellsprache | `test_core.py::test_single_speaker_same_language` | grün |
| S2 | zwei Sprecher | `test_core.py::test_two_speakers_assigned` | grün |
| S3 | zwei Sprachen, dritte Zielsprache | `test_core.py::test_multilingual_translation` | grün |
| S4–S12 | Fehlerfälle, Export, Determinismus | siehe EVIDENCE-P0 | grün |
| S15, S27, S28, S30, S31 | Ordner, Kataloge, Sprache, Doku, Lizenzen | siehe EVIDENCE-P0 | grün |
| P1-Zusatz | echte Modelle auf echter Sprache | `tests/test_integration_models.py` (5 Tests, Marker `integration`) | **5 grün, echter Lauf** |

Nicht gebaut und nicht geprüft: S13/S14 (Streaming, P3), S16–S19/S22 (Galerie, P2),
S20 (Video, P4), S21 (Oberfläche, P6), S23–S26 (HTTP, P5).

## 3. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **94 Tests, 94 grün** (5 Integrationstests abgewählt) |
| Integrationstests | `uv run pytest -m integration` | **5 grün** mit echten Modellen |
| Coverage | `uv run pytest --cov=transcriber --cov-report=term` | **809 Zeilen, 20 nicht abgedeckt, 98 %** |
| Typen | `uv run mypy` | keine Fehler (strict, 16 Dateien) |
| Lint | `uv run ruff check` | keine Befunde |
| Mutation | `uv run python tools/run_mutants.py` | **16 von 17 getötet**; Überlebender ist äquivalent (Gleichstand-Regel) |
| Zufällige Reihenfolge | `--randomly-seed={1,42,4711}` | 3 von 3 grün |
| Echter CLI-Lauf | `transcriber transcribe jfk.wav` mit echten Modellen | Exit 0, 21 s, 14,9 GB RSS |

Nicht abgedeckt (20 Zeilen): Innereien der Adapter, die nur mit geladenem Modell laufen
(`builtin.py` Zeilen für `diarize()` und Token-/Shim-Ränder). Sie werden von den
Integrationstests ausgeführt, die nicht in der Coverage-Messung stehen.

## 4. Echter Lauf, Zahlen und Text

Eingabe: `jfk.wav` (11,0 s, 16 kHz mono, gemeinfreie Aufnahme), Zielsprache Deutsch.

```
$ uv run transcriber transcribe ~/.cache/transcriber/samples/jfk.wav \
    --config echt.toml --out echt-out --format json --format srt
Geschrieben: echt-out/jfk.json
Geschrieben: echt-out/jfk.srt
Fertig: 1 Segmente, 1 Sprecher, 1 Sprachen.
Exit status: 0 · Elapsed: 0:21.01 · Maximum resident set size: 14.907.688 KB
```

Ergebnis (Auszug aus `jfk.srt`):

```
1
00:00:00,000 --> 00:00:10,380
[S1] Und so, meine amerikanischen Mitbürger, fragen Sie nicht, was Ihr Land für Sie tun kann,
fragen Sie, was Sie für Ihr Land tun können.
```

| Feld | Wert |
|---|---|
| `text` | „And so, my fellow Americans, ask not what your country can do for you, ask what you can do for your country." |
| `translations.de` | „Und so, meine amerikanischen Mitbürger, fragen Sie nicht, was Ihr Land für Sie tun kann, fragen Sie, was Sie für Ihr Land tun können." |
| `language` / `language_confidence` | `en` / 0,83 |
| `translated_from` | `en` |
| Sprecher | 1 (`S1`), 10,38 s Sprachanteil |
| Laufzeit einzeln gemessen | Whisper 1,0 s für 11 s Ton; MADLAD 9,5 s laden + 1,1 s übersetzen; Gesamtlauf 21 s inklusive Modellwechsel |

Speicher: Spitzenwert 14,9 GB RSS, davon rund 6 GB Modellgewichte nacheinander.
Der Host hat 31 GB. Ein Hintergrundprozess mit kleinem cgroup-Limit wurde beim ersten Versuch
vom OOM-Killer beendet (Beweis: `journalctl` „Memory cgroup out of memory", PID des pytest).
Deshalb läuft der schwere Lauf im Vordergrund, und `device_map` verhindert die zusätzliche
fp32-Kopie im RAM.

## 5. Fehler, die dieser Schritt gefunden hat

Alle fünf waren echte Inkompatibilitäten, keine Testfehler:

1. **PyAV 19 gegen faster-whisper 1.2.1.** `decode_audio()` übergibt `metadata_errors`,
   PyAV 19 kennt das nicht. Festlegung `av<17` (16.1.0).
2. **pyannote.audio 4.0.7 gegen den freigegebenen Modellnamen.** `from_pretrained("...-3.1")`
   lädt in 4.x still `speaker-diarization-community-1` (CC-BY-4.0, gated). Festlegung
   `pyannote.audio<4` (3.4.0). Das ist eine Lizenzfrage, nicht nur eine technische.
3. **torchaudio 2.11 gegen pyannote 3.4.** `torchaudio.AudioMetaData` fehlt. Festlegung
   `torch<2.9`, `torchaudio<2.9` (2.8.0+cu128). Der eigene Ton-Lader nutzt deshalb PyAV,
   nicht torchaudio.
4. **huggingface_hub 2.3 gegen pyannote 3.4.** pyannote ruft `hf_hub_download(use_auth_token=…)`,
   hub 2.x kennt nur `token`. Ein schmaler Shim übersetzt das Argument, beschränkt auf
   `pyannote.*` und `huggingface_hub*`.
5. **torch ≥ 2.6 lädt pyannote-Checkpoints nicht mehr ohne Freigabe.** `TorchVersion`,
   `Specifications`, `Problem`, `Resolution`, `Task` werden über
   `torch.serialization.add_safe_globals` freigegeben — nur diese Klassen, nichts weiter.

Zusätzlich gefunden: MADLAD lud ohne `device_map` die fp32-Kopie zusätzlich in den RAM
(12,9 GB RSS) und starb im Hintergrundprozess. Mit `device_map="cuda"` und
`low_cpu_mem_usage=True` lädt es Gewicht für Gewicht auf die GPU.

## 6. Bekannte Grenzen

- **Nur eine Sprecherdatei getestet.** `jfk.wav` hat einen Sprecher; pyannote findet korrekt
  einen. Die Güte bei mehreren Sprechern ist **nicht** gemessen. Dafür braucht es echte
  Mehrsprecheraufnahmen — die kann ich nicht erfinden.
- **Kurze Datei.** 11 s. Eine Stunde Ton ist nicht gemessen; die Laufzeitschätzung aus dem
  SPEC (3–5 min ASR je Stunde) ist weiter eine Schätzung.
- **Sprach-ID-Güte.** Ein Treffer (`en`, 0,83 bei der CLI, 0,40 bei 3 s Ausschnitt). Keine
  Messung über viele Dateien, keine Verwechslungsmatrix.
- **Übersetzungsgüte.** Ein Satz, korrekt. Keine Messung (kein BLEU, kein Referenzkorpus).
- **MADLAD-Sprachliste ist eine Auswahl** (82 Codes), nicht alle 400+. Unbekannte Codes werden
  abgelehnt (S4). Das ist eine bewusste Grenze, kein Fehler.
- **`pip-audit` weiter nicht gelaufen.** Kein Schwachstellen-Scan der Abhängigkeiten.
- **ffmpeg bleibt ein GPL-Build.** Siehe `LICENSES.md`.

## 7. Wiederholbar

```bash
uv sync
uv run python tools/fetch_samples.py          # lädt jfk.wav nach ~/.cache/transcriber/samples
uv run pytest                                  # 94 Tests ohne Modelle
uv run pytest -m integration                   # 5 Tests mit Modellen (im Vordergrund, ~30 s)
uv run pytest --cov=transcriber --cov-report=term
uv run mypy && uv run ruff check
uv run python tools/run_mutants.py
```

Versionen: Python 3.12.14, torch 2.8.0+cu128, torchaudio 2.8.0, pyannote.audio 3.4.0,
faster-whisper 1.2.1, transformers 5.21.0, huggingface-hub 2.3.0, av 16.1.0,
speechbrain 1.1.2, CUDA-Treiber 580.178.04. Genaue Stände in `uv.lock`.
