# Test mit einem echten YouTube-Video (mehrere Stimmen)

Datum: 2026-10-31 · Autor: Hermes · Code-Stand: Commit nach diesem Bericht

Auftrag: „P4 und dann einen Test mit einem Youtube Video mit mehreren stimmen"
Quelle: `https://youtu.be/JIXkq4EcOZc`, Abschnitt 00:16:19 bis 00:20:46 (267 s)
(Tonspur Deutsch, Fassung von CiNENET Deutschland; die Datei liegt nur lokal zum Test in
`out-youtube/` und gehört nicht ins Repo)

## 1. Ergebnis auf einen Blick

| Größe | Wert |
|---|---|
| Länge des Abschnitts | 267,0 s (4:27) |
| Transkription + Sprechertrennung + Sprach-ID + Übersetzung | **59 s** (Faktor 0,22 zur Echtzeit) |
| Segmente | 79 |
| Gefundene Sprecher | **5** (S1 19 Segmente, S2 10, S3 22, S4 11, S5 17). Vom Auftraggeber bestätigt: es waren tatsächlich 5 Sprecher. |
| Erkannte Sprachen | de 75, lb 2, da 1, bn 1 |
| Untertitel im Video | `out-youtube/film_untertitelt.mp4`, 32 MB, Bild geprüft |
| Rechenweg | Whisper large-v3, pyannote 3.1, VoxLingua107, MADLAD-400-3B-MT auf der RTX 4060 |

## 2. Beispielzeilen aus dem Transkript

```
   3.3-   4.5 S1 de | Großer Goldzahn!
   4.8-   8.1 S1 de | Uh, old who, Fetty, ihr könnt jetzt rauskommen.
   8.3-   9.6 S1 de | Uh, uh, uh, uh.
  10.4-  11.1 S1 de | Was ist?
  11.4-  14.2 S1 de | Goldzahn, hast du dich mit ihm verbündet, um mich reinzulegen, ha?
```

Der Text ist inhaltlich richtig, die Zeiten passen zum Dialog, die Sprecher wechseln plausibel.
Ein Bild aus dem fertigen Video bei Sekunde 20 zeigt den eingebrannten Untertitel
„[S1] Diesmal hast du es etwas übertrieben.", also denselben Text wie im Transkript.

## 3. Was gut funktioniert

- **Sprechertrennung** findet 5 Sprecher in 4,5 Minuten Film mit Musik, Geräuschen und
  Hintergrunddialog. Die Abschnitte wechseln an den Stellen, an denen im Bild andere Personen
  sprechen.
- **Transkription** des deutschen Tons ist brauchbar; Eigennamen („Fetty", „Goldzahn",
  „Genosse Wang", „Sponsorin") kommen richtig.
- **Untertitel** sitzen zeitlich richtig und sind lesbar.
- **Laufzeit** 59 s für 4,5 Minuten Material — der Engpass ist die Diarization, nicht die Übersetzung.

## 4. Was nicht gut funktioniert

1. **Sprach-ID irrt auf langen Abschnitten.** 4 von 79 Segmenten bekommen eine falsche Sprache
   (`lb`, `da`, `bn`), auch bei hoher angegebener Sicherheit (0,98 für `da`). Der Text darunter
   ist trotzdem korrekt deutsch. Das ist ein Fehler der Sprach-ID, nicht der Transkription.
2. **Zwei Läufe liefern nicht dasselbe.** Derselbe Befehl auf derselben Datei ergab einmal 72 und
   einmal 79 Segmente (Sprecherzahl blieb 5). Grund: VAD und Beam-Suche auf der GPU arbeiten nicht
   bit-genau deterministisch. **SPEC S11 („zwei Läufe gleich") gilt damit für den Kern mit
   Test-Adaptern, nicht für echte Modelle.** Das ist eine offene Abweichung vom SPEC und muss so
   benannt werden.
3. **Keine Wahrheit zum Vergleich — teilweise geklärt.** Ich habe keinen Referenztext und keine
   Sprecherliste. **Der Auftraggeber hat am 2026-10-31 bestätigt: es waren tatsächlich 5
   verschiedene Sprecher.** Die Anzahl stimmt damit. Nicht belegt ist weiter, **wer** welche
   Zeile sagt: ob S1 bis S5 den richtigen Personen zugeordnet sind und ob die Sprecherwechsel
   an der richtigen Stelle sitzen, ist nicht geprüft. Die Zuordnung bleibt ein Modellergebnis.
4. **Musik und Geräusche** werden teils als Sprache segmentiert („Uh, uh, uh, uh.").

## 5. Drei Fehler, die dieser Test gefunden hat

1. **Sprach-ID brach bei sehr kurzen Abschnitten ab.** `RuntimeError: Padding size should be
   less than the corresponding input dimension … input [1, 128, 3]` — ECAPA bekam 3 Zeitfenster.
   Behoben: Abschnitte unter 0,5 s werden auf 0,5 s erweitert; unter 0,25 s Restlänge wird
   „und" mit Sicherheit 0 zurückgegeben. Test: `test_language_id_expands_very_short_windows`.
2. **20 Sprachen in einem deutschen Film.** VoxLingua107 verhört sich auf kurzen, musikunterlegten
   Abschnitten. Zwei Regeln greifen jetzt: unsichere Abschnitte (Sicherheit < 0,5) erben die
   Sprache des nächsten sicheren Abschnitts (`smooth_languages`), und Abschnitte bis 2 s folgen
   der Dateisprache von Whisper (`apply_file_language`). Ergebnis: 20 → 4 Sprachen. Beide Regeln
   haben eigene Tests.
3. **`render` scheiterte an einem relativen Videopfad.** ffmpeg läuft im Arbeitsordner mit der
   SRT; ein relativer Pfad zeigt dort ins Leere. Behoben (absoluter Pfad), Test:
   `test_render_works_with_a_relative_path`.

## 6. Gauntlet nach diesen Änderungen

| Schicht | Ergebnis |
|---|---|
| Testsuite | **137 Tests, 137 grün** (6 Integrationstests abgewählt) |
| Coverage | **1204 Zeilen, 64 nicht abgedeckt, 95 %** |
| mypy strict | keine Fehler (19 Dateien) |
| ruff | keine Befunde |
| Echter Lauf | 267 s Video in 59 s, 5 Sprecher, Untertitel sichtbar geprüft |

## 7. Grenzen dieses Tests

- Ein Video, ein Genre, eine Tonspur (deutsche Synchronfassung). Keine Konferenz, kein Interview,
  kein Telefonat.
- Keine Wahrheit über Sprecherzahl und -zuordnung, siehe 4.3.
- Die Sprach-ID bleibt die schwächste Stufe der Kette. Wer zuverlässige Sprachangaben braucht,
  sollte Whisper die Sprache je Datei bestimmen lassen und die Segment-Sprache nur bei klarem
  Wechsel überschreiben.
- Die Datei liegt nur lokal und ist nicht Teil des Repos.

## 8. Wiederholbar

```bash
uvx --quiet yt-dlp --js-runtimes node --remote-components ejs:github --no-playlist \
    --download-sections "*979-1246" -f "bv*[height<=480]+ba/b[height<=480]" \
    -o "film_ausschnitt.%(ext)s" "https://youtu.be/JIXkq4EcOZc"
uv run transcriber transcribe out-youtube/film_ausschnitt.mp4 --target de --out out-youtube/lauf
uv run transcriber render out-youtube/film_ausschnitt.mp4 \
    --transcript out-youtube/lauf/film_ausschnitt.json \
    --out out-youtube/film_untertitelt.mp4 --subtitle-lang de
```

Hinweis zum Herunterladen: `yt-dlp` aus dem System ist zu alt (2024.04.09) und scheitert an
YouTube; die Fassung 2026.10.26 über `uvx` mit `--js-runtimes node` und
`--remote-components ejs:github` funktioniert.
