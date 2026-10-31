# EVIDENCE — Stufe P6 (Weboberfläche)

Datum: 2026-10-31 · Autor: Hermes · SPEC: `SPEC.md` Abschnitt 3.2, Abnahme S21, S29

Freigabe: „Jetzt P6, im Anschluss eine umfängliche sachlich professionelle README.md auf Englisch.
Lizenz MIT, Push in ein GitHub Repo".

## 1. Was gebaut ist

| Baustein | Inhalt |
|---|---|
| `ui.ApiClient` | dünner HTTP-Klient: Aufträge anlegen, auflisten, lesen, löschen, Export-Adresse |
| `ui.build_view()` | Steuerbaum der Oberfläche; gibt die Wurzel zurück, damit Tests ohne Browser prüfen können |
| `ui.run_ui()` | Start im Web-Modus (`flet.AppView.WEB_BROWSER`) auf `127.0.0.1` |
| `ui.gallery_people()` / `ui.delete_person()` | Lesen und Löschen der Galerie ohne Modell |
| Befehl | `transcriber ui [--api URL] [--port P] [--gallery PFAD] [--lang de\|en]` |
| Texte | neun neue Schlüssel (`ui.*`) in `de.json` und `en.json` |

Inhalt der Oberfläche: Datei hochladen, Auftragsliste mit Zustand, Transkript anzeigen, Personen der
Galerie mit Zahl der Stimmabdrücke, Löschen je Person, Umschalter Deutsch/Englisch. Die Oberfläche
enthält keine Fachlogik; sie spricht ausschließlich über HTTP mit dem Dienst aus P5.

## 2. Abnahmekriterien

| Nr | Kriterium | Test | Ergebnis |
|---|---|---|---|
| S21 | Oberfläche startet im Web-Modus, Seite lädt mit HTTP 200, Auftragsliste sichtbar, Zustand abfragbar | `tests/test_ui.py` (8 Tests) plus echter Start, siehe Abschnitt 3 | grün |
| S29 | Umschaltung Deutsch/Englisch wirkt in der Oberfläche | `test_ui.py::test_view_switches_language`, `test_labels_in_both_languages` | grün |

Einzelne Prüfungen in `tests/test_ui.py`:

| Test | Prüft |
|---|---|
| `test_labels_in_both_languages` | Beschriftungen in beiden Sprachen |
| `test_view_shows_jobs_from_the_service` | Auftrag anlegen, warten, Liste zeigt Dateinamen im Steuerbaum |
| `test_view_shows_people_and_deletes_them` | Person erscheint, Löschen entfernt sie aus der Galerie |
| `test_view_switches_language` | deutscher und englischer Steuerbaum, aktive Sprache |
| `test_view_survives_an_unreachable_service` | toter Dienst: keine Ausnahme, Meldung „Dienst nicht erreichbar" |
| `test_transcript_is_rendered` | Zeilenformat `[start-ende] Sprecher: Text` |
| `test_export_url_points_at_the_service` | Exportadresse zeigt auf den Dienst |
| `test_gallery_module_is_reachable_without_models` | Galerie lesbar ohne Modellstart |

Die Tests laufen gegen einen **echten** `uvicorn`-Server auf einem freien Port, nicht gegen einen
Ersatz. Damit ist der HTTP-Weg der Oberfläche mitgeprüft.

## 3. Echter Lauf

```
$ uv run transcriber ui --port 8561 --gallery /tmp/tc-real/stream-galerie.db &
$ curl -s -o ui.html -w "HTTP %{http_code}  %{size_download} Bytes\n" http://127.0.0.1:8561/
HTTP 200  1462 Bytes
```

Ausgeliefert wird die Flet-Startseite; die Oberfläche selbst läuft als Flutter-Web-Client im
Browser. Geprüft ist damit: der Web-Modus startet, bindet und liefert die Anwendung aus. **Nicht**
geprüft ist die Darstellung im Browser — dafür fehlt in dieser Umgebung ein sichtbarer Client.

## 4. Gauntlet

| Schicht | Befehl | Ergebnis |
|---|---|---|
| Testsuite | `uv run pytest` | **161 grün**, 6 Integrationstests abgewählt, 5,77 s |
| Coverage | `uv run pytest --cov=transcriber` | **1794 Anweisungen, 166 offen, 91 %** |
| Typen | `uv run mypy` | keine Fehler, 23 Dateien |
| Lint | `uv run ruff check` | keine Befunde |

Neue Mutanten für die Oberfläche wurden **nicht** ergänzt. Begründung: `ui.py` enthält keine
Fachentscheidung; die geprüfte Logik liegt in `service.py` und `gallery.py`, und dort sind die
Mutanten vorhanden. Der Mutantenstand bleibt bei 26/30.

## 5. Fehler, die dieser Schritt gefunden hat

1. **`httpx.ASGITransport` ist asynchron.** Der erste Testaufbau konnte den synchronen Klienten
   nicht daran hängen. Jetzt startet der Test einen echten `uvicorn`-Server im Hintergrund. Das ist
   mehr Aufwand, prüft aber den wirklichen Weg.
2. **`ApiClient` ist ein `slots`-Dataclass.** Ein Test wollte die App als Attribut anhängen; das
   ging nicht. Der Test hält App und Klient jetzt in einem eigenen Objekt.
3. **Textsuche im Steuerbaum war zu flach.** Sie sah nur direkte Kinder; die Texte liegen in
   `Row`-Kindern. Jetzt läuft die Suche rekursiv.
4. **`flet` fehlte** als Abhängigkeit; ergänzt, mit Typprüfungs-Aussetzer.

## 6. Bekannte Grenzen

- **Keine Sichtprüfung im Browser.** Belegt sind Start, HTTP 200 und der Steuerbaum; Aussehen,
  Scrollen und Klickverhalten im Browser sind ungeprüft.
- **Upload-Knopf ohne Dateiauswahl.** `build_view` nimmt eine Rückruffunktion entgegen; der fertige
  Dateiwähler von Flet ist nicht angeschlossen. Für den Betrieb ist der Weg über `POST /jobs` oder
  die Kommandozeile vollständig.
- **Kein Auftragsfortschritt in Prozent**, nur Zustand und Fehlertext.
- **Keine Anmeldung.** Die Oberfläche ist so offen wie der Dienst darunter.
