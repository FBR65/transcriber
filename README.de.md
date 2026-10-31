# Transcriber

Lokale Transkription von Ton und Video mit Sprechertrennung, Spracherkennung je Abschnitt,
Übersetzung, Stimmabdruck-Galerie, laufendem Ton, eingebrannten Untertiteln, HTTP-Dienst und
Weboberfläche. Jeder Baustein ist ein austauschbares Plug-in. Kein Cloud-Dienst ist beteiligt; die
Modelle laufen auf der GPU des lokalen Rechners.

- Version: 0.1.0
- Lizenz: MIT (siehe `LICENSE`)
- Python: 3.12
- Plattform der Messungen in dieser Datei: Linux, NVIDIA RTX 4060 Laptop (8 GB), 31 GB RAM

## Stand

Alle sechs geplanten Stufen sind gebaut. Jedes Abnahmekriterium aus `SPEC.md` gehört zu einem
benannten Test und wurde, wo ein echter Lauf möglich war, auf echtem Material ausgeführt.

| Stufe | Inhalt | Beleg |
|---|---|---|
| P0 | Kern, Datenmodell, Adapter-Registry, Exporte, Kommandozeile | `EVIDENCE-P0.md` |
| P1 | ASR, Diarization, Sprach-ID, Übersetzung mit echten Modellen | `EVIDENCE-P1.md` |
| P2 | Stimmabdruck-Galerie: Anmeldung mit Zustimmung, Löschen, Sperre | `EVIDENCE-P2.md` |
| P3 | Streaming mit VAD, Mikrofon, Sprecherverfolgung | `EVIDENCE-P3.md` |
| P4 | Eingebrannte Untertitel | `EVIDENCE-P4.md`, `EVIDENCE-YOUTUBE.md` |
| P5 | HTTP-Dienst (FastAPI): Aufträge, Export, WebSocket-Strom | `EVIDENCE-P5.md` |
| P6 | Weboberfläche (Flet) | Abschnitt „Tests und Qualität" |

## Was es tut

Ein Lauf macht aus einer Ton- oder Videodatei ein Transkript:

- Abschnitte mit Start und Ende,
- eine Sprecherkennung je Abschnitt (`S1`, `S2`, … ; ein Name, wenn die Galerie die Stimme kennt),
- die erkannte Sprache je Abschnitt,
- den Originaltext,
- eine Übersetzung je Zielsprache.

Das Ergebnis gibt es als JSON, SRT, VTT und reinen Text. Es kommt über HTTP, erscheint in der
Weboberfläche oder wird als Untertitel ins Video gebrannt.

## Architektur

Der Kern kennt nur Schnittstellen. Adapter werden über ihren Namen in einer Konfigurationsdatei
gewählt und erst geladen, wenn sie gebraucht werden.

| Port | Aufgabe | Standardadapter |
|---|---|---|
| `AsrEngine` | Ton → Text mit Zeiten | `faster-whisper` (large-v3) |
| `Diarizer` | Ton → Sprecherwechsel | `pyannote` (speaker-diarization-3.1) |
| `LanguageId` | Abschnitt → Sprache | `voxlingua` (ECAPA auf VoxLingua107) |
| `Translator` | Text → Zielsprache | `madlad` (MADLAD-400-3B-MT) |
| `Voiceprint` | Abschnitt → Stimmabdruck, Galerie-Treffer | `wespeaker` |
| `Vad` | Ton → Sprachabschnitte (Streaming) | `energy` (ohne Modell), `silero` |
| `Exporter` | Transkript → Datei | `json`, `srt`, `vtt`, `txt` |
| `VideoRenderer` | Video + Untertitel → Video | `ffmpeg` (libass) |
| `UiApp` | Weboberfläche | `flet` |

Regeln für den ganzen Code:

- Der Kern importiert keinen ML-Code. Modelle werden im Konstruktor des Adapters importiert.
- Adapter werden je Stufe erzeugt und danach freigegeben. Whisper und der 3B-Übersetzer liegen auf
  einer 8-GB-GPU nie gleichzeitig im Speicher.
- Ein Plug-in aus einem fremden Paket meldet sich über die Python-Einstiegspunktgruppe
  `transcriber.adapters` an; eine Änderung am Kern ist nicht nötig.
- Adapter auflisten oder eine Konfiguration prüfen berührt keine GPU.

## Installation

```bash
git clone <dieses Repository>
cd transcriber
uv sync
```

`uv sync` installiert den festgelegten Satz. Die Versionsgrenzen sind Absicht; die Gründe stehen in
`LICENSES.md` und `SPEC.md` Abschnitt 9:

| Grenze | Grund |
|---|---|
| `pyannote.audio<4` | 4.x lädt für `speaker-diarization-3.1` ein anderes, gated Modell unter anderer Lizenz |
| `torch<2.9`, `torchaudio<2.9` | pyannote 3.4 braucht `torchaudio.AudioMetaData`, ab 2.9 entfernt |
| `av<17` | faster-whisper 1.2.1 übergibt `metadata_errors`, PyAV 17 kennt das nicht |

Zwei Modelle sind auf Hugging Face gated. Bedingungen einmal annehmen für
`pyannote/speaker-diarization-3.1` und `pyannote/segmentation-3.0`, dann den Token dort ablegen, wo
der Code ihn liest:

```bash
install -m 600 /dev/null ~/.cache/huggingface/token
printf '%s' 'hf_...' > ~/.cache/huggingface/token
```

Der erste Lauf lädt etwa 10 GB Modellgewichte nach `~/.cache/huggingface`.

## Benutzung

### Kommandozeile

```bash
# eine Datei oder ein ganzer Ordner, JSON und SRT
uv run transcriber transcribe aufnahme.mp3 --target de --out out --format json --format srt

# mehrere Zielsprachen auf einmal
uv run transcriber transcribe vortrag.wav --target de --target en --out out

# mit Stimmabdruck-Galerie: bekannte Sprecher bekommen ihre Namen
uv run transcriber transcribe besprechung.m4a --target de --gallery ~/.local/share/transcriber/gallery.db

# Galerie verwalten
uv run transcriber gallery enroll stimme.wav --name "Frau Beispiel" --consent
uv run transcriber gallery list
uv run transcriber gallery delete "Frau Beispiel"

# Untertitel ins Video brennen
uv run transcriber render vortrag.mp4 --transcript out/vortrag.json --out out/vortrag.gebrannt.mp4 --subtitle-lang de

# Streaming: Datei oder Mikrofon, Ereignisse während der Ton ankommt
uv run transcriber stream --source aufnahme.wav --out out
uv run transcriber stream --source mic --seconds 30 --out out

# lokaler HTTP-Dienst und Weboberfläche
uv run transcriber serve --port 8000
uv run transcriber ui --port 8550 --api http://127.0.0.1:8000

# was vorhanden ist und unter welcher Lizenz
uv run transcriber adapters
uv run transcriber licenses
```

Exit-Codes: `0` Erfolg, `1` Verarbeitungsfehler (etwa unlesbare Datei), `2` Benutzungsfehler
(unbekannte Zielsprache, fehlende Zustimmung, unbekannter Adapter). Ein Ordnerlauf bricht bei der
ersten schlechten Datei nicht ab; er meldet die Datei und macht weiter.

### Python-API

```python
from transcriber import RunConfig, export, run_file

transcript = run_file(
    "aufnahme.mp3",
    config=RunConfig(
        asr="faster-whisper",
        diarizer="pyannote",
        language_id="voxlingua",
        translator="madlad",
        voiceprint=None,
        target_languages=["de"],
    ),
)
export(transcript, "out", formats=("json", "srt"))
```

### HTTP-Dienst

| Methode | Pfad | Aufgabe |
|---|---|---|
| `POST` | `/jobs` | Datei hochladen, liefert `job_id` |
| `GET` | `/jobs` | alle Aufträge mit Zustand |
| `GET` | `/jobs/{id}` | Zustand: `queued`, `running`, `done`, `failed` plus Fehlertext |
| `GET` | `/jobs/{id}/transcript` | Transkript als JSON |
| `GET` | `/jobs/{id}/export/{fmt}` | `json`, `srt`, `vtt`, `txt` |
| `DELETE` | `/jobs/{id}` | Auftrag und seine Dateien löschen |
| `WS` | `/stream` | roher float32-Ton hinein (16 kHz, mono), JSON-Ereignisse heraus |
| `GET` | `/openapi.json` | Selbstbeschreibung |

Der Dienst bindet an `127.0.0.1`, außer `--host` sagt etwas anderes. Er hat keine Anmeldung und
kein TLS: gedacht für den lokalen Rechner.

### Streaming-Protokoll

Der WebSocket-Endpunkt nimmt Ton als rohe Little-Endian-float32-Blöcke bei 16 kHz, mono. Eine leere
Nachricht bedeutet Ende des Tons; danach gibt der Dienst den letzten Abschnitt aus und schließt.
Jedes Ereignis trägt `index`, `start_s`, `end_s`, `speaker`, `language`, `text`, `is_final`.

## Ausgabeformat

```json
{
  "schema_version": 1,
  "mode": "file",
  "created_at": "2026-10-31T15:20:00+00:00",
  "source": {
    "path": "/abs/pfad/aufnahme.mp3",
    "sha256": "…",
    "duration_s": 267.0,
    "sample_rate_hz": 16000,
    "channels": 1
  },
  "config": {
    "asr": "faster-whisper",
    "diarizer": "pyannote",
    "language_id": "voxlingua",
    "translator": "madlad",
    "voiceprint": "wespeaker",
    "gallery": "/home/benutzer/.local/share/transcriber/gallery.db",
    "target_languages": ["de"]
  },
  "speakers": [
    {"id": "S1", "name": "Frau Beispiel", "voiceprint_match": 0.954,
     "speech_s": 30.8, "segment_count": 19}
  ],
  "segments": [
    {"id": "seg-0001", "start_s": 3.32, "end_s": 4.5, "speaker": "S1",
     "language": "de", "language_confidence": 0.98,
     "text": "Großer Goldzahn!",
     "translations": {"de": "Großer Goldzahn!"},
     "translated_from": null, "is_final": true}
  ],
  "warnings": []
}
```

Regeln: `text` ist immer das Original. `translations` bildet Sprache auf Text ab; ein Abschnitt in
einer Zielsprache trägt dort denselben Text. `translated_from` ist `null`, wenn keine Übersetzung
nötig war. Abschnitte sind sortiert und überlappen nicht. Stimmabdrücke stehen nie in der Ausgabe,
nur Name und Ähnlichkeit.

## Modelle und Lizenzen

Alle Bausteine sind kommerziell nutzbar. Die Tabelle mit Quellen, Daten und den genauen
API-Aufrufen steht in `LICENSES.md`; die Pflicht-Namensnennung in `NOTICE`.

| Zweck | Modell | Lizenz |
|---|---|---|
| Spracherkennung | Systran/faster-whisper-large-v3 | MIT |
| Sprechertrennung | pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0 | MIT (gated) |
| Sprecher-Einbettung | pyannote/wespeaker-voxceleb-resnet34-LM | CC-BY-4.0, Namensnennung nötig |
| Sprach-Identifikation | speechbrain/lang-id-voxlingua107-ecapa | Apache-2.0 |
| Übersetzung | google/madlad400-3b-mt | Apache-2.0 |

Abgelehnt, weil nicht kommerziell nutzbar: `facebook/nllb-200-*` und
`facebook/seamless-m4t-v2-large` (CC-BY-NC-4.0), `nvidia/diar_sortformer_4spk-v1` (CC-BY-NC-4.0).

`transcriber licenses` gibt die Tabelle aus; ein Test schlägt fehl, wenn eine NC-Lizenz in die
Standardkonfiguration gerät.

## Stimmabdruck-Galerie und Datenschutz

Stimmabdrücke sind biometrische Daten. Nach DSGVO Art. 9 brauchen sie eine Rechtsgrundlage. Das ist
Betreiberpflicht, nicht Aufgabe der Software. Die Software setzt den technischen Teil durch:

- Anmeldung nur mit ausdrücklicher Zustimmung (`--consent`); ohne sie wird nichts gespeichert,
- Löschen je Person nach Name oder Kennung, mit `PRAGMA secure_delete` und `VACUUM` danach,
- die Galerie ist eine lokale SQLite-Datei mit Rechten 600 in einem Verzeichnis mit Rechten 700,
- Stimmabdrücke verlassen den Rechner nie und stehen nie in einem Transkript,
- gleichzeitige Schreiber werden geordnet; ein eindeutiger Index auf den Namen verhindert Dubletten.

## Konfiguration

```toml
[adapters]
asr = "faster-whisper"
diarizer = "pyannote"
language_id = "voxlingua"
translator = "madlad"
voiceprint = "wespeaker"     # leerer Text schaltet die Galerie ab

[gallery]
path = "/home/benutzer/.local/share/transcriber/gallery.db"

[targets]
languages = ["de"]
```

Übergeben mit `--config datei.toml`. Angaben auf der Kommandozeile schlagen die Datei.

## Ein Plug-in schreiben

```python
# my_plugin/__init__.py
from transcriber.ports import AsrSegment
from transcriber.registry import Registry


class MyAsr:
    def transcribe(self, path, options=None):
        return [AsrSegment(0.0, 1.0, "hallo", "de")]

    def release(self):
        pass


def register(registry: Registry) -> None:
    registry.register("asr", "my-asr", MyAsr)
```

```toml
[project.entry-points."transcriber.adapters"]
my_plugin = "my_plugin:register"
```

`examples/demo-plugin` ist ein lauffähiges Beispiel mit festen Adaptern ohne Modelle; es prüft die
ganze Kette (Dekodieren, Export, HTTP, Untertitel) ohne GPU.

## Sprachen

Die Doku gibt es in Englisch (`README.md`) und Deutsch (`README.de.md`) mit gleicher
Abschnittsstruktur; ein Test prüft das. Meldungen, Kommandozeile und Weboberfläche lassen sich mit
`--lang` und dem Umschalter zwischen Deutsch und Englisch wechseln; Standard ist Deutsch.
Technische Kennungen (`S1`, `job_id`, Feldnamen, Exit-Codes) werden nie übersetzt.

Sprachbehandlung im Transkript: Whisper bestimmt die Sprache der ganzen Datei und ist darin
robust. Ein Abschnitt behält eine andere Sprache nur, wenn er mindestens 3 Sekunden lang ist und
die Sprach-ID mindestens 80 % sicher ist. Bei einem deutsch synchronisierten Film sank die Zahl
gemeldeter Sprachen damit von 20 auf 4.

## Tests und Qualität

```bash
uv run pytest                        # Unit-Tests, ohne Modelle, ohne Netz
uv run pytest -m integration        # echte Modelle auf einer gemeinfreien Probe
uv run pytest --cov=transcriber     # Coverage
uv run mypy                         # strict
uv run ruff check
uv run python tools/run_mutants.py   # Handmutanten gegen die Suite
```

Gemessener Stand bei Version 0.1.0:

| Aspekt | Wert |
|---|---|
| Unit-Tests | 161, alle grün |
| Integrationstests | 6, alle grün (echte Modelle auf `jfk.wav`) |
| Coverage | 91 % von 1794 Anweisungen |
| Typen | mypy strict, keine Befunde, 23 Dateien |
| Lint | ruff, keine Befunde |
| Mutation | 26 von 30 Mutanten getötet; die 4 Überlebenden sind dokumentierte Äquivalente |
| Echter Tonlauf | 11 s Ton in 21 s inklusive Modellstart, 14,9 GB Spitzenspeicher |
| Echter Videolauf | 267 s Filmausschnitt in 59 s, 5 Sprecher, Untertitel eingebrannt |
| HTTP-Lauf | Upload → fertig → Transkript → SRT → Löschen, mit echten Modellen |
| Weboberfläche | liefert HTTP 200 im Web-Modus |

Die Integrationssuite braucht einmal `tools/fetch_samples.py` (lädt 11 Sekunden gemeinfreien Ton)
und etwa 10 GB Modellgewichte.

## Laufzeit und Grenzen

Gemessen auf einer RTX 4060 Laptop mit 8 GB VRAM:

- 267 s Filmton: 59 s Verarbeitung (Faktor 0,22 zur Echtzeit), 5 Sprecher gefunden, gegen die Angabe
  des Nutzers bestätigt.
- Der Modellstart dominiert kurze Dateien: 11 s Ton brauchen rund 21 s insgesamt.
- Whisper und der 3B-Übersetzer passen nicht gleichzeitig in 8 GB; der Kern lädt und gibt sie Stufe
  für Stufe frei. Streaming läuft aus demselben Grund ohne Übersetzung.
- Zwei Läufe auf derselben Datei sind **nicht** identisch: VAD und Beam-Suche auf der GPU rechnen
  nicht bit-genau. Beobachtet: 72 und 79 Segmente bei gleicher Eingabe. Der Kern ist deterministisch
  und als solcher geprüft; echte Modellausgaben sind eine Näherung.

Bekannte Grenzen:

- Die **Identität** der Sprecher ist über die Zählung hinaus nicht geprüft: ohne Referenzliste ist
  die Zuordnung von Kennung zu Person unbelegt.
- Die Spracherkennung je Abschnitt irrt bei musiklastigem Material gelegentlich noch.
- Der HTTP-Dienst hat keine Anmeldung und hält Aufträge nur im Speicher; ein Neustart verliert sie.
- Der WebSocket-Strom sendet rohe float32-Blöcke; ein fertiger Browser-Client gehört nicht zum
  Projekt.
- Eingebrannte Untertitel haben eine Gestaltung für alle Sprecher, unten mittig.
- Video wird neu kodiert (`libx264`, CRF 20); die Bildqualität gegen die Quelle wurde nicht gemessen.

## Projektaufbau

```
src/transcriber/
  core.py            Dateilauf: ASR → Sprechertrennung → Sprache → Übersetzung
  stream.py          Streaming-Lauf mit VAD und Sprecherverfolgung
  models.py          pydantic-Datenmodell, geprüft
  registry.py        Adapter-Registry, Einstiegspunkte
  gallery.py         Stimmabdruck-Galerie (SQLite, Zustimmung, Löschen, Sperre)
  exporters.py       JSON, SRT, VTT, TXT
  service.py         FastAPI-Anwendung und Auftragsverwaltung
  ui.py              Flet-Weboberfläche und HTTP-Klient
  adapters/          Modelladapter, VAD, Toneinlesen, ffmpeg-Renderer
  i18n/              deutsche und englische Meldungskataloge
tests/               Unit-, Randfall-, Eigenschafts-, Integrations- und Diensttests
tools/               Beispiel-Download, Mutantenläufer, YouTube-Test
SPEC.md              der Vertrag: Umfang, Datenmodell, Abnahmekriterien
EVIDENCE-*.md        was gebaut, was gemessen, was nicht belegt ist
LICENSES.md          Lizenzprüfung mit Datum und Quellen
NOTICE               Namensnennung, die die Lizenzen verlangen
```

## Lizenz

MIT, siehe `LICENSE`. Fremde Bausteine behalten ihre eigenen Lizenzen; siehe `LICENSES.md` und
`NOTICE`.

Der auf dem Entwicklungsrechner verwendete `ffmpeg`-Build ist ein GPL-Build (`--enable-gpl`). Die
eigene Nutzung ist unproblematisch; wer das Produkt mit diesem Build weitergibt, löst GPL-Pflichten
aus und sollte einen LGPL-Build mitliefern.

## Hinweise für die Entwicklung

- `SPEC.md` ist der Vertrag. Jedes Abnahmekriterium (S1…S31) gehört zu einem benannten Test.
  Verhaltensänderungen gehen zuerst durch die Spezifikation.
- Jede Stufe endet mit einem Belegbericht: ausgeführte Befehle, echte Ausgabe, und was nicht geprüft
  wurde.
- Der Mutantenläufer ändert Quelldateien und stellt sie wieder her; nicht starten, während im selben
  Verzeichnis ein Testlauf aktiv ist.
