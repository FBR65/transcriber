# SPEC — Transkriptionssystem mit Sprechertrennung, Übersetzung, Galerie, Streaming und Oberfläche

Stand: 2026-10-28 · Fassung 2 · Status: **wartet auf Freigabe** · Autor: Hermes

Gegenüber Fassung 1 geändert: D9 = c (Stimmabdruck-Galerie in v1), D10 = b (Echtzeit und Mikrofon
in v1), D11 = keine Festlegung (neutrales Datenmodell), D12 = b (eingebrannte Untertitel),
D13 = b (Web-Oberfläche mit Flet), D14 = b (Ordner rekursiv). Die Lizenzprüfung aus Fassung 1
bleibt gültig und ist um Flet, Silero-VAD und sounddevice ergänzt.

## 1. Ziel

Ein System macht aus Ton ein Transkript. Es erkennt Sprecher, erkennt Sprachen je Abschnitt,
übersetzt in eine oder mehrere Zielsprachen und erkennt bekannte Sprecher an der Stimme wieder.
Es arbeitet mit Dateien und mit laufendem Ton (Mikrofon, Stream). Andere Systeme binden es als
Bibliothek, über die Kommandozeile, über Daten oder über die Oberfläche ein. Jeder Baustein ist
ein austauschbares Plug-in.

## 2. Umfang v1

| Punkt | Stand |
|---|---|
| Audiodateien: wav, mp3, m4a, ogg, flac, mp4 (Tonspur) | im Umfang |
| Sprechertrennung, Kennungen `S1`, `S2` … | im Umfang |
| Sprache je Segment | im Umfang |
| Übersetzung in eine oder mehrere Zielsprachen, Datenmodell neutral | im Umfang (D11) |
| Export: JSON, SRT, VTT, TXT | im Umfang |
| Python-API, CLI, Konfigurationsdatei | im Umfang |
| Ordner rekursiv, Fehler je Datei | im Umfang (D14) |
| Echtzeit: Mikrofon und Stream | im Umfang (D10) |
| Stimmabdruck-Galerie: Sprecher über Dateien wiedererkennen, Namen | im Umfang (D9 = c) |
| Eingebrannte Untertitel in Video | im Umfang (D12) |
| Web-Oberfläche mit Flet | im Umfang (D13) |
| HTTP-Service (FastAPI) als offene Schnittstelle | **im Umfang (D4 = b)** |

## 3. Architektur (Ports und Adapter)

Kern plus Adapter. Der Kern kennt nur Schnittstellen. Jeder Adapter ist ein Plug-in mit Namen.

| Port | Aufgabe | Standard-Adapter v1 | Lizenz |
|---|---|---|---|
| `AsrEngine` | Ton → Text mit Zeit | `faster-whisper` large-v3 | MIT |
| `Diarizer` | Ton → Sprecherwechsel mit Zeit | `pyannote` 3.1 | MIT |
| `LanguageId` | Tonabschnitt → Sprache | `voxlingua` ECAPA | Apache-2.0 |
| `Translator` | Text → Zielsprache | `madlad` (MADLAD-400-3B-MT) | Apache-2.0 |
| `Voiceprint` | Tonabschnitt → Stimmabdruck, Vergleich mit Galerie | `wespeaker` + Galerie | CC-BY-4.0 |
| `Vad` | Ton → Sprachblöcke (nur Betriebsart `stream`) | `silero` | MIT |
| `StreamSource` | Mikrofon, Datei, stdin → Tonblöcke | `sounddevice`, `file` | MIT |
| `Exporter` | Transkript → Datei | `json`, `srt`, `vtt`, `txt` | eigene Arbeit |
| `VideoRenderer` | Video + Untertitel → Video mit eingebrannten Untertiteln | `ffmpeg` | GPL-Build, siehe 6 |
| `UiApp` | Oberfläche | `flet` | Apache-2.0 |

Regeln:

- Ein Adapter wird über seinen Namen in der Konfiguration gewählt. Ein Wechsel ändert keinen Code.
- Neue Adapter melden sich über den Einstiegspunkt `transcriber.adapters` an. Ein Plug-in aus
  einem fremden Paket braucht keine Änderung am Kern.
- Der Kern lädt Adapter erst beim Lauf. Fehlt ein Paket oder ein Modell, kommt eine klare Meldung
  mit Adapter-Namen. Der Kern startet trotzdem.
- Ein Adapter bekommt nur Daten und seine Optionen. Er kennt den Kern nicht.
- Zwei Betriebsarten teilen denselben Kern: `file` (ganze Datei) und `stream` (laufender Ton).
  Beide liefern dieselbe Ereignisform.
- Der HTTP-Service ist **kein Adapter**. Er ist eine weitere Schnittstelle auf dieselbe
  öffentliche API des Kerns. Er enthält keine Fachlogik.

### 3.1 HTTP-Schnittstelle (D4 = b)

| Methode | Pfad | Aufgabe |
|---|---|---|
| POST | `/jobs` | Datei hochladen, Auftrag anlegen, Antwort `{job_id}` |
| GET | `/jobs` | Liste der Aufträge mit Zustand |
| GET | `/jobs/{job_id}` | Zustand: `queued`, `running`, `done`, `failed`, plus Fehlertext |
| GET | `/jobs/{job_id}/transcript` | Transkript als JSON (Abschnitt 4) |
| GET | `/jobs/{job_id}/export/{format}` | Export als json, srt, vtt, txt |
| DELETE | `/jobs/{job_id}` | Auftrag und Ausgabe löschen |
| WS | `/stream` | Ton hinein, Ereignisse heraus (Betriebsart `stream`) |
| GET | `/openapi.json` | Selbstbeschreibung nach OpenAPI |

Der Dienst läuft lokal. Ohne ausdrückliche Option `--host` bindet er nur an `127.0.0.1`.

### 3.2 Sprache der Meldungen und der Doku (D6 = c)

- Meldungen der Kommandozeile, Fehlertexte und Oberflächentexte liegen in Katalogen:
  `i18n/de.json` und `i18n/en.json`. Ein Schlüssel, zwei Texte.
- Standardsprache ist **Deutsch**. Umschalten mit `--lang en` (CLI) und über einen Umschalter
  in der Oberfläche. Die Wahl gilt für den Lauf, nicht dauerhaft.
- Jeder Schlüssel muss in beiden Katalogen stehen. Ein Test prüft die Vollständigkeit.
- Doku zweisprachig: `README.md` (Englisch, primär) und `README.de.md` (Deutsch). Beide haben
  dieselben Abschnitte in derselben Reihenfolge. Ein Test prüft die Gleichheit der Überschriften.
- Technische Kennungen (`S1`, `job_id`, Feldnamen, Exit-Codes) werden nicht übersetzt.

## 4. Datenmodell (JSON, `schema_version: 1`)

```
transcript:
  schema_version: 1
  mode: "file" | "stream"
  source: {path, sha256, duration_s, sample_rate_hz, channels}
  config: {asr, diarizer, language_id, translator, voiceprint, target_languages: ["de"]}
  speakers: [
    {id: "S1", name: "Herr X" | null, voiceprint_match: 0.91 | null,
     speech_s, segment_count}
  ]
  segments: [
    {id, start_s, end_s, speaker, language, language_confidence,
     text, translations: {de: "…", en: "…"}, translated_from, is_final}
  ]
  warnings: ["…"]
```

Regeln:

- `text` ist immer der Originaltext. `translations` ist eine Map Sprache → Text. Ist die
  Segment-Sprache gleich einer Zielsprache, steht dort derselbe Text. Bei einer Zielsprache hat
  die Map einen Eintrag. Das Schema bricht bei mehreren Sprachen nicht (D11).
- `translated_from` ist die erkannte Quellsprache des Segments.
- `language_confidence` liegt zwischen 0 und 1.
- `name` ist nur gesetzt, wenn die Galerie den Sprecher sicher erkennt. Ohne Treffer bleibt
  `name` leer und `id` bleibt `S1`, `S2` ….
- `voiceprint_match` ist die Ähnlichkeit (0–1) oder `null`. Der Stimmabdruck selbst steht
  **nie** im Transkript.
- Zeiten sind Sekunden als Fließkommazahl, `end_s > start_s`. Segmente sind nach `start_s`
  sortiert und überschneiden sich nicht.
- In der Betriebsart `stream` hat jedes Ereignis `is_final: false` und wird nach Abschluss des
  Abschnitts mit `is_final: true` erneut ausgegeben.

## 5. Verhalten (Abnahmekriterien)

Jede Zeile wird ein Test. Der Testname steht in Klammern.

| Nr | Eingabe | Erwartetes Ergebnis | Test |
|---|---|---|---|
| S1 | Eine Datei, ein Sprecher, Zielsprache = Dateisprache | Ein Sprecher `S1`, `translations[de] == text`, `translated_from == null` (`test_single_speaker_same_language`) |
| S2 | Datei mit zwei Sprechern im Wechsel | Segmente tragen `S1` und `S2`, jeder Sprecher hat mindestens ein Segment, Reihenfolge = Zeitachse (`test_two_speakers_assigned`) |
| S3 | Datei mit zwei Sprachen, Zielsprache = dritte Sprache | Jedes Segment hat `language` und `translations` in der Zielsprache, `translated_from` = Segment-Sprache (`test_multilingual_translation`) |
| S4 | Zielsprache nicht in der Sprachliste des Übersetzers | `UnsupportedLanguageError` mit Liste, CLI Exit 2 (`test_unsupported_target_language`) |
| S5 | Konfiguration nennt unbekannten Adapter-Namen | `UnknownAdapterError` mit Liste der registrierten Namen (`test_unknown_adapter_name`) |
| S6 | Konfiguration tauscht den Übersetzer gegen einen Test-Adapter | Lauf nutzt den neuen Adapter, Ausgabe bleibt schema-konform (`test_adapter_swap_translator`) |
| S7 | Export nach json, srt, vtt, txt | Jede Datei nicht leer und gültig, SRT und VTT mit Zeitmarken und Sprecherkennung (`test_export_formats`) |
| S8 | Dieselbe Datei über Python-API und CLI | Ausgaben gleich, ausgenommen `created_at` (`test_api_cli_parity`) |
| S9 | Beschädigte Datei, kein Tonstrom | `AudioDecodeError`, Exit 1, keine Ausgabedatei (`test_corrupt_audio`) |
| S10 | Stille Datei | Lauf ohne Ausnahme, `segments == []`, `warnings` gefüllt (`test_silent_audio`) |
| S11 | Zwei Läufe, gleiche Eingabe und Konfiguration | Alle Felder außer `created_at` gleich (`test_deterministic_output`) |
| S12 | Zwei Segmente mit gleicher Textlänge, Sprecherwechsel dazwischen | Zuordnung folgt der maximalen zeitlichen Überschneidung (`test_overlap_assignment_rule`) |
| S13 | `stream`, 20 s Datei blockweise eingespeist | Mindestens ein Ereignis vor Ende der Einspeisung, letztes Ereignis beim Abschluss, jedes Ereignis vollständig (`test_stream_incremental_events`) |
| S14 | `stream` mit Zielsprache | Übersetzung je Ereignis, nicht erst am Ende (`test_stream_translation_per_block`) |
| S15 | Ordner mit drei Dateien, eine beschädigt | Zwei Transkripte, ein Fehler je Datei, kein Abbruch, Exit 1 (`test_folder_partial_failure`) |
| S16 | Galerie mit zwei angemeldeten Sprechern, danach neue Datei derselben Sprecher | Segmente tragen die Namen, `voiceprint_match` über der Schwelle (`test_gallery_recognizes_known_speakers`) |
| S17 | Galerie gefüllt, Datei mit fremdem Sprecher | Fremder Sprecher bleibt `S3`, `name == null`, Warnung „unbekannter Sprecher" (`test_gallery_unknown_speaker`) |
| S18 | Person aus der Galerie löschen, danach gleiche Datei | Treffer verschwindet, Sprecher gilt als unbekannt, kein Rest in der Galerie-Datei (`test_gallery_delete_person`) |
| S19 | Galerie ohne Zustimmung | Anmeldung eines Stimmabdrucks ohne Schalter `--consent` schlägt fehl, nichts wird gespeichert (`test_gallery_requires_consent`) |
| S20 | Video mit Untertiteln rendern | Ausgabe hat Bild- und Tonstrom, Laufzeit ±0,1 s zur Quelle, Bildbereich mit Untertitel weicht vom Quellbild ab (`test_burned_in_subtitles`) |
| S21 | Oberfläche im Web-Modus starten | Seite lädt (HTTP 200), Liste der Aufträge sichtbar, Upload legt Auftrag an, Status ist abfragbar (`test_ui_web_mode`) |
| S22 | Gleichzeitiger Zugriff zweier Prozesse auf die Galerie | Kein beschädigter Stand, zweiter Schreiber wartet oder meldet Konflikt (`test_gallery_locking`) |
| S23 | Datei über `POST /jobs`, dann Zustand abfragen bis `done` | Antwort enthält `job_id`; `GET /jobs/{id}` endet mit `done`; Transkript abrufbar und schema-konform (`test_http_job_roundtrip`) |
| S24 | Beschädigte Datei über HTTP | Zustand `failed` mit Fehlertext, keine halbe Ausgabe, Dienst läuft weiter (`test_http_corrupt_upload`) |
| S25 | `GET /openapi.json` | Gültige Selbstbeschreibung, enthält die Pfade aus Abschnitt 3.1 (`test_http_openapi_schema`) |
| S26 | Dienst ohne `--host` starten | Bindet nur an `127.0.0.1`, nicht an alle Adressen (`test_http_binds_localhost`) |
| S27 | Beide Sprachkataloge laden | Gleiche Schlüsselmenge in `de.json` und `en.json`, kein leerer Text (`test_i18n_keys_complete`) |
| S28 | CLI mit `--lang en` auf einen Fehlerfall | Meldung erscheint in Englisch und enthält die technische Kennung unverändert; ohne `--lang` erscheint Deutsch (`test_cli_language_switch`) |
| S29 | Oberfläche, Sprachumschalter | Nach dem Umschalten ändern sich sichtbare Texte, Feldnamen und Kennungen bleiben gleich (`test_ui_language_switch`) |
| S30 | `README.md` und `README.de.md` | Beide vorhanden, gleiche Überschriften in gleicher Reihenfolge (`test_docs_bilingual_parity`) |

## 6. Lizenzprüfung (Stand 2026-10-28, über HF-API, PyPI und GitHub)

Bedingung: alles kommerziell nutzbar.

| Komponente | Quelle | Lizenz | Kommerziell | Bemerkung |
|---|---|---|---|---|
| `faster-whisper`, `CTranslate2` | PyPI / GitHub | MIT | ja | — |
| `Systran/faster-whisper-large-v3` | HF | MIT | ja | keine Freigabe nötig |
| `pyannote.audio` (Code) | GitHub CNRS | MIT | ja | — |
| `pyannote/speaker-diarization-3.1`, `segmentation-3.0` | HF | MIT | ja | gated, Token nötig |
| `pyannote/wespeaker-voxceleb-resnet34-LM` | HF | CC-BY-4.0 | ja | Namensnennung im NOTICE |
| `speechbrain`, `lang-id-voxlingua107-ecapa` | PyPI / HF | Apache-2.0 | ja | Trainingsdaten aus YouTube-Mitschnitten, Restrisiko notiert |
| `google/madlad400-3b-mt` | HF | Apache-2.0 | ja | 400+ Sprachen |
| `silero-vad` | PyPI / GitHub snakers4 | MIT | ja | VAD für Streaming |
| `sounddevice` | PyPI / GitHub spatialaudio | MIT | ja | Mikrofon |
| `flet` | PyPI / GitHub flet-dev | Apache-2.0 | ja | Oberfläche, Flutter-Kern |
| `fastapi` | PyPI / GitHub fastapi | MIT | ja | HTTP-Schnittstelle |
| `uvicorn` | PyPI / GitHub encode | BSD-3 | ja | ASGI-Server |
| `python-multipart` | PyPI / GitHub Kludex | Apache-2.0 | ja | Datei-Upload |
| `websockets` | PyPI / GitHub python-websockets | BSD-3 | ja | Streaming-Endpunkt |
| `httpx` (nur Tests) | PyPI | BSD-3 | ja | HTTP-Testclient |
| `numpy` | PyPI | BSD-3 | ja | — |
| `transformers`, `tokenizers`, `safetensors` | PyPI | Apache-2.0 | ja | — |
| `torch`, `torchaudio` | PyPI | BSD-3 (PyTorch-Variante) | ja | — |
| `av`, `soundfile` | PyPI | BSD-3 | ja | — |
| `typer`, `pydantic`, `huggingface-hub` | PyPI | MIT / MIT / Apache-2.0 | ja | — |
| `ffmpeg` (Host-Build 9.0.1) | lokal | **GPL-Build** (`--enable-gpl`) | Nutzung ja | Eigene Nutzung unproblematisch. Wer das Produkt mit diesem Build weitergibt, muss GPL erfüllen. Für Weitergabe: LGPL-Build einplanen. |
| `facebook/nllb-200-*` | HF | CC-BY-NC-4.0 | **nein** | aus dem Plan entfernt |
| `facebook/seamless-m4t-v2-large` | HF | CC-BY-NC-4.0 | **nein** | nicht verwendet |
| `nvidia/diar_sortformer_4spk-v1` | HF | CC-BY-NC-4.0 | **nein** | nicht verwendet |

Pflichten daraus: `LICENSES.md` mit dieser Tabelle und Prüfdatum, `NOTICE` mit Namensnennung für
das Wespeaker-Modell und PyTorch, Hinweis auf den GPL-Build von ffmpeg in `README`.

## 7. Rechtliche Pflichten der Galerie (Stimmabdrücke)

Stimmabdrücke sind biometrische Daten. Nach DSGVO Art. 9 brauchen sie eine Rechtsgrundlage.
Ich bin kein Jurist. Diese Punkte sind technische Pflichten im SPEC, keine Rechtsberatung:

- Anmeldung eines Sprechers nur ausdrücklich, mit Schalter `--consent`. Ohne Zustimmung wird
  nichts gespeichert (S19).
- Löschbefehl je Person und für die ganze Galerie. Die Löschung entfernt den Datensatz
  vollständig (S18).
- Galerie liegt lokal in einer Datei, Rechte 600. Kein Versand von Stimmabdrücken über Netzwerk.
- Stimmabdrücke stehen nie im Transkript. Nur Name und Ähnlichkeitswert (Abschnitt 4).
- Die Oberfläche zeigt, welche Personen gespeichert sind, und bietet Löschen an.
- Betreiberpflicht: Information der betroffenen Personen, Löschfristen, Verzeichnis der
  Verarbeitungstätigkeiten. Das liegt bei dir, nicht im Code.

## 8. Grenzen (Invarianten)

- Der Kern importiert keinen ML-Code. Nur Adapter importieren Modelle.
- Ohne Netzwerk läuft ein Lauf, wenn die Modelle lokal liegen.
- Kein Adapter schreibt in das Quellverzeichnis.
- Ein Adapter darf abstürzen. Der Kern fängt den Fehler, nennt den Adapter und bricht ab.
  Kein halbes Transkript.
- Ein Sprecher ohne Treffer in der Galerie wird nie mit einem Namen versehen.
- Bestehende Tests bleiben grün. Öffentliche Signaturen aus Abschnitt 3 bleiben stabil.

## 9. Entscheidungen

| ID | Frage | Empfehlung / Stand |
|---|---|---|
| D1 | Standard-ASR: large-v3, large-v3-turbo, whisper.cpp | **entschieden am 2026-10-28: a** — faster-whisper large-v3, int8_float16, ca. 3 GB VRAM. Turbo bleibt als Option in der Konfiguration |
| D2 | Sprechertrennung | **entschieden: pyannote 3.1.** **Zugang freigeschaltet und geprüft am 2026-10-28:** `config.yaml` beider Repos HTTP 200, Gewichte-Download von `segmentation-3.0` (5,9 MB) und `wespeaker-voxceleb-resnet34-LM` (26,6 MB) HTTP 206 mit dem Token von Konto `FBR-65` |
| D3 | Übersetzer: MADLAD-400-3B, M2M-100, Opus-MT | **entschieden am 2026-10-28: a** — MADLAD-400-3B-MT, Apache-2.0 |
| D4 | HTTP-Service in v1 | **entschieden am 2026-10-28: b** — FastAPI in v1, Pfade in Abschnitt 3.1, Abnahme S23–S26 |
| D5 | Plug-in-Mechanismus: entry points oder Klassenpfad | **entschieden am 2026-10-28: a** — entry points plus Registry |
| D6 | Sprache von Doku und Meldungen | **entschieden am 2026-10-28: c** — Doku zweisprachig (`README.md` Englisch, `README.de.md` Deutsch), Meldungen und Oberfläche in Deutsch und Englisch umschaltbar, Standard Deutsch. Regeln in Abschnitt 3.2, Abnahme S27–S30 |
| D7 | MIT-Lizenz, privates Repo | **entschieden am 2026-10-28: a** — MIT für den eigenen Code, privates Repo |
| D8 | Lizenzwächter im Code | **entschieden am 2026-10-28: a** — `transcriber licenses` plus Test gegen NC-Lizenzen |
| D9 | Stimmerkennung | **entschieden: c** — volle Galerie in v1, Pflichten in Abschnitt 7 |
| D10 | Echtzeit | **entschieden: b** — Betriebsart `stream` mit Mikrofon und Stream |
| D11 | Zielsprachen | **keine Festlegung** — neutrales Schema mit Map, CLI nimmt `--target` mehrfach |
| D12 | Video | **entschieden: b** — eingebrannte Untertitel, Port `VideoRenderer` |
| D13 | Oberfläche | **entschieden: b** — Flet (`https://github.com/flet-dev/flet`), Apache-2.0 |
| D14 | Mehrere Dateien | **entschieden: b** — Ordner rekursiv, Fehler je Datei |

## 10. Lieferstufen

Der Umfang ist jetzt groß. Ich baue in dieser Reihenfolge. Jede Stufe endet mit grünen Tests
und einem kurzen Bericht. Du kannst nach jeder Stufe stoppen.

| Stufe | Inhalt | Prüfbar durch |
|---|---|---|
| P0 | Gerüst: Datenmodell, Registry, Konfiguration, CLI (`file`), Export, Fehlerfälle | S4–S12 |
| P1 | Modelle: ASR, Diarization, Sprach-ID, Übersetzung | S1–S3, echter Lauf auf einer echten Datei |
| P2 | Galerie: Stimmabdruck, Anmeldung, Löschen, Sperre | S16–S19, S22 |
| P3 | Streaming: VAD, Mikrofon, Ereignisse | S13, S14 |
| P4 | Video mit eingebrannten Untertiteln | S20 |
| P5 | HTTP-Service mit Aufträgen und Streaming-Endpunkt | S23–S26 |
| P6 | Flet-Oberfläche im Web-Modus, nutzt die HTTP-Schnittstelle | S21 |

Grobe Schätzung: P0 und P1 zusammen 1–2 Tage Arbeit, P2 etwa 1 Tag, P3 1–2 Tage (der teuerste
Teil), P4 ein halber Tag, P5 ein halber bis ein Tag, P6 1 Tag. Schätzung, keine Zusage.
Ich messe nach jeder Stufe.

## 11. Setup-Plan (freizugeben mit dem SPEC)

| Schritt | Inhalt | Begründung |
|---|---|---|
| venv | `uv venv --python 3.12`, alle Aufrufe über `uv run` | Host hat 3.14; torch/ctranslate2 liefern Räder für 3.12 |
| Laufzeit-Pakete | `faster-whisper`, `pyannote.audio`, `transformers`, `torch` (cu12x), `speechbrain`, `silero-vad`, `sounddevice`, `flet`, `fastapi`, `uvicorn`, `python-multipart`, `websockets`, `numpy`, `soundfile`, `av`, `typer`, `pydantic` | je ein Paket pro Port plus CLI, Oberfläche, HTTP, Ton |
| Test und Prüfung | `pytest`, `pytest-cov`, `pytest-randomly`, `httpx`, `mypy`, `ruff`, `mutmut` oder Handmutanten | Gauntlet nach old-coder |
| Modelle | Download nach `~/.cache/huggingface` beim ersten Lauf, ca. 9–10 GB | kein Modell im Repo |
| HF-Token | `~/.cache/huggingface/token`, Rechte 600, nicht im Repo, nicht in Logs | gated pyannote-Modelle |
| Lizenzen | `LICENSES.md`, `NOTICE`, Hinweis zum GPL-Build in `README` | Abschnitt 6 |
| Git | `git init`, MIT für den eigenen Code, Commit bei SPEC und je Stufe | Rückverfolgbarkeit |
| Hardware | RTX 4060 mit 8 GB, 31 GB RAM, ffmpeg vorhanden | geprüft am 2026-10-28 |

Speicher-Notiz: large-v3 und MADLAD-3B laufen nicht gleichzeitig im Speicher. Der Kern lädt
Stufen nacheinander und gibt Speicher frei. Das ist Teil des Plans, kein Zufall.

## 12. Gauntlet

Tier 3. Volle Schleife, Property-Tests für das Datenmodell, Mutation, echter Lauf auf echter
Datei und echtem Mikrofon, adversarischer Durchgang (Stille, 6 Kanäle, 3 Stunden, Datei ohne
Endung, abgezogenes Mikrofon, Galerie-Datei beschädigt). Kein Erfolg ohne EVIDENCE-Bericht.

## 13. Freigabe

Ich baue nichts, bevor du diesen SPEC freigibst.

1. Freigabe des SPEC, oder Änderungswünsche. **Alle Entscheidungen D1–D14 sind damit beantwortet.**
2. Für D2: Annahme der Bedingungen für `pyannote/speaker-diarization-3.1` und
   `pyannote/segmentation-3.0` auf huggingface.co. Ohne Freigabe bleibt die Sprechertrennung
   gesperrt und P1 kann nicht abgeschlossen werden.
