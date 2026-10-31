# EVIDENCE — Stufe P5 (HTTP-Dienst)

Datum: 2026-10-31 · Autor: Hermes · SPEC: `SPEC.md` Abschnitt 3.1, Abnahme S23–S26

Freigabe: „Nun P5".

## 1. Was gebaut ist

| Baustein | Inhalt |
|---|---|
| `service.create_app()` | FastAPI-App, Aufträge über einen Arbeitsthread (die GPU arbeitet ohnehin seriell) |
| `JobManager` | Aufträge annehmen, zwischenspeichern, nacheinander ausführen, löschen; jeder Auftrag hat einen eigenen Ordner |
| Pfade | `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/transcript`, `GET /jobs/{id}/export/{fmt}`, `DELETE /jobs/{id}`, `WS /stream`, `GET /openapi.json` |
| Zustände | `queued`, `running`, `done`, `failed` mit Fehlertext |
| CLI | `transcriber serve [--host H] [--port P] [--config DATEI]` |
| Bindung | ohne `--host`: `127.0.0.1` (S26) |
| Streaming | WebSocket nimmt rohe float32-Blöcke (16 kHz mono); eine leere Nachricht beendet den Ton; Ereignisse kommen als JSON |
| Speicher | Der Dienst lädt kein Modell beim Start; das passiert beim ersten Auftrag |

## 2. Abnahmekriterien

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S23 | Upload → Zustand `done` → Transkript schema-konform | `test_service.py::test_job_roundtrip` | grün |
| S24 | beschädigte Datei → `failed` mit Fehlertext, Dienst lebt weiter | `test_service.py::test_corrupt_upload_fails_without_killing_the_service` | grün, zweiter Auftrag danach `done` |
| S25 | `/openapi.json` listet die Pfade | `test_service.py::test_openapi_lists_the_documented_paths` | grün |
| S26 | ohne `--host` nur localhost | `test_service.py::test_service_defaults_to_localhost` (prüft die Vorgabewerte in Dienst und CLI) | grün |

Weitere Tests: fremder Dateityp wird abgelehnt (422), leerer Upload (422), unbekannter Auftrag (404), unbekanntes Exportformat (422), Löschen entfernt den Auftrag (204, danach 404), WebSocket liefert ein Ereignis.

## 3. Echter Lauf mit echten Modellen über HTTP

Dienst auf Port 8765, echte Modelle (faster-whisper, pyannote, VoxLingua, MADLAD), Datei `jfk.wav`:

```
$ curl -s http://127.0.0.1:8765/openapi.json  →  ["/jobs", "/jobs/{job_id}",
                                                   "/jobs/{job_id}/export/{fmt}",
                                                   "/jobs/{job_id}/transcript"]
$ curl -F "file=@jfk.wav" http://127.0.0.1:8765/jobs
job=5e294f11f695425cbdeaf594d8b82bce   state=done
$ curl http://127.0.0.1:8765/jobs/<id>/transcript
modus file | dauer 11.0
  0.0-10.4 S1 en | And so, my fellow Americans, ask not what your country can d…
                 | DE: Und so, meine amerikanischen Mitbürger, fragen Sie nicht, was Ihr Land…
$ curl http://127.0.0.1:8765/jobs/<id>/export/srt
1
00:00:00,000 --> 00:00:10,380
[S1] Und so, meine amerikanischen Mitbürger, fragen Sie nicht, was Ihr Land für Sie tun kann,…
$ curl -X DELETE … → 204 ; danach GET → 404
```

Damit ist der ganze Weg über HTTP mit echten Modellen belegt: Upload, Warteschlange, Transkript,
Export, Löschen.

## 4. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **153 Tests, 153 grün** (6 Integrationstests abgewählt) |
| Coverage | `uv run pytest --cov=transcriber` | **1673 Zeilen, 133 nicht abgedeckt, 92 %**; `service.py` 93 % |
| Typen | `uv run mypy` | keine Fehler (22 Dateien) |
| Lint | `uv run ruff check` | keine Befunde |
| Mutation | `uv run python tools/run_mutants.py` | **26 von 30 getötet**; die 4 Überlebenden sind dokumentierte Äquivalente aus P0 und P2 |
| Echter Lauf | Dienst + curl | Exit 0, siehe Abschnitt 3 |

Neue Mutanten dieser Stufe, alle getötet: unfertiger Auftrag liefert trotzdem ein Transkript,
fremder Dateityp wird angenommen, Löschen lässt den Auftrag stehen, unbekanntes Exportformat wird
durchgelassen, Dienst bindet an alle Adressen.

## 5. Fehler, die dieser Schritt gefunden hat

1. **WebSocket-Test lief in eine Sackgasse.** Der Dienst wartete auf weitere Tonblöcke, der Client
   auf ein Ereignis. Behoben durch eine feste Regel: eine **leere Nachricht bedeutet Ende des
   Tons**. Damit ist das Protokoll eindeutig statt zeitabhängig.
2. **`serve` fehlte als Abhängigkeit.** FastAPI war eingebunden, `uvicorn` nicht. Ergänzt,
   zusammen mit einem Typprüfungs-Aussetzer für dieses Paket.
3. **Erster WebSocket-Entwurf las im Hintergrundthread direkt vom Socket.** Das ist nicht
   zulässig. Jetzt liest die asynchrone Seite und schiebt Bytes durch eine Warteschlange an den
   Arbeitsthread.

## 6. Bekannte Grenzen

- **Ein Arbeitsthread.** Zwei Aufträge laufen nacheinander, nicht parallel. Für eine GPU richtig,
  für viele kleine Dateien langsam. Die Warteschlange ist nicht dauerhaft: ein Neustart verliert
  alle Aufträge (kein Wiedereinspielen von der Platte).
- **Kein Auth, kein TLS.** Der Dienst ist für localhost gedacht; `--host 0.0.0.0` öffnet ihn ohne
  jede Absicherung. Das ist im SPEC so nicht ausgeschlossen und muss vor jedem fremden Zugriff
  bedacht werden.
- **WebSocket ohne Übersetzung.** Aus Speichergründen (8 GB VRAM) übersetzt der Stream nicht.
- **WS-Protokoll ist roh:** float32-Blöcke, 16 kHz, mono. Ein Browser-Client muss selbst
  umrechnen; ein fertiger Client fehlt.
- **`pip-audit` weiter nicht gelaufen.**

## 7. Wiederholbar

```bash
uv run pytest                                  # 153 Tests
uv run transcriber serve --port 8000 &         # bindet 127.0.0.1
curl -F "file=@datei.wav" http://127.0.0.1:8000/jobs
curl http://127.0.0.1:8000/jobs/<id>/transcript
```
