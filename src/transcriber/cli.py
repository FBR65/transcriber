"""Kommandozeile. Alle Meldungen über i18n, Standard Deutsch."""

from __future__ import annotations

import itertools
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import typer

from .audio import AUDIO_SUFFIXES, probe
from .config import DEFAULT_ADAPTERS, load_settings
from .core import release, run_file
from .errors import TranscriberError
from .exporters import EXPORTERS, export
from .i18n import normalize_language, translate
from .licensing import LICENCES
from .models import Transcript
from .registry import DEFAULT_REGISTRY

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Transkription mit Sprechertrennung und Übersetzung.",
)


def _collect(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(
                sorted(
                    candidate
                    for candidate in path.rglob("*")
                    if candidate.is_file() and candidate.suffix.lower() in AUDIO_SUFFIXES
                )
            )
        elif path.is_file():
            files.append(path)
    return files


@app.command()
def transcribe(
    paths: list[str] = typer.Argument(None, help="Audiodateien oder Ordner."),
    target: list[str] = typer.Option(None, "--target", "-t", help="Zielsprache, mehrfach möglich."),
    config: str | None = typer.Option(None, "--config", "-c", help="TOML-Konfiguration."),
    out: str | None = typer.Option(None, "--out", "-o", help="Zielordner."),
    gallery: str | None = typer.Option(None, "--gallery", help="Pfad der Galerie-Datei."),
    fmt: list[str] = typer.Option(None, "--format", "-f", help="json, srt, vtt, txt."),
    lang: str = typer.Option("de", "--lang", help="Sprache der Meldungen: de oder en."),
) -> None:
    """Transkribiert Dateien und Ordner."""
    language = normalize_language(lang)
    requested = list(paths or [])
    if not requested:
        typer.echo(translate("error.no_input", language))
        raise typer.Exit(code=2)

    try:
        settings = load_settings(Path(config) if config else None, lang=language)
    except (OSError, tomllib.TOMLDecodeError) as error:
        typer.echo(translate("error.generic", language, detail=str(error)))
        raise typer.Exit(code=1) from error

    run_config = settings.run
    if target:
        run_config = run_config.model_copy(update={"target_languages": list(target)})
    if gallery:
        run_config = run_config.model_copy(update={"gallery": gallery})
    formats = list(fmt or ["json"])
    unknown = [name for name in formats if name not in EXPORTERS]
    if unknown:
        typer.echo(translate("error.generic", language, detail=f"format: {', '.join(unknown)}"))
        raise typer.Exit(code=2)

    missing = [item for item in requested if not Path(item).exists()]
    for item in missing:
        typer.echo(translate("error.not_a_file", language, path=item))

    files = _collect(requested)
    if not files:
        typer.echo(translate("error.no_input", language))
        raise typer.Exit(code=1 if missing else 2)

    out_dir = Path(out) if out else Path.cwd()
    exit_code = 1 if missing else 0
    for path in files:
        try:
            transcript = run_file(path, config=run_config, lang=language)
            written = export(transcript, out_dir, formats)
        except TranscriberError as error:
            typer.echo(
                translate(
                    "cli.failed", language, path=str(path), message=error.localized(language)
                )
            )
            exit_code = max(exit_code, error.exit_code)
            continue
        for written_path in written:
            typer.echo(translate("cli.written", language, path=written_path))
        typer.echo(
            translate(
                "cli.done",
                language,
                segments=len(transcript.segments),
                speakers=len(transcript.speakers),
                languages=len({segment.language for segment in transcript.segments}),
            )
        )
    raise typer.Exit(code=exit_code)


@app.command()
def adapters() -> None:
    """Zeigt registrierte Adapter je Port."""
    DEFAULT_REGISTRY.discover()
    ports = DEFAULT_REGISTRY.ports()
    typer.echo(translate("cli.adapters"))
    if not ports:
        typer.echo(translate("cli.no_adapters"))
        return
    for port in ports:
        names = ", ".join(DEFAULT_REGISTRY.names(port)) or "-"
        typer.echo(f"  {port}: {names}")


@app.command()
def licenses() -> None:
    """Zeigt die Lizenz der Standardmodelle (D8)."""
    typer.echo(translate("cli.licenses"))
    for entry in LICENCES:
        marker = "ja" if entry.commercial else "NEIN"
        typer.echo(f"  {entry.port:12} {entry.model:48} {entry.licence:12} kommerziell: {marker}")


@app.command()
def ui(
    api: str = typer.Option("http://127.0.0.1:8000", "--api", help="Adresse des Dienstes."),
    port: int = typer.Option(8550, "--port", help="Port der Oberfläche."),
    gallery: str | None = typer.Option(None, "--gallery", help="Pfad der Galerie-Datei."),
    lang: str = typer.Option("de", "--lang", help="Sprache der Oberfläche: de oder en."),
) -> None:
    """Startet die Oberfläche im Web-Modus."""
    from .ui import run_ui

    run_ui(api=api, port=port, lang=normalize_language(lang), gallery_path=gallery)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Adresse. Ohne Angabe nur lokal."),
    port: int = typer.Option(8000, "--port", help="Port."),
    config: str | None = typer.Option(None, "--config", "-c", help="TOML-Konfiguration."),
) -> None:
    """Startet den HTTP-Dienst (SPEC Abschnitt 3.1)."""
    from .service import serve as run_service

    run_service(host=host, port=port, config_path=Path(config) if config else None)


@app.command()
def stream(
    source: str = typer.Option(..., "--source", "-s", help="Datei oder „mic“ für das Mikrofon."),
    target: list[str] = typer.Option(None, "--target", "-t", help="Zielsprache, mehrfach möglich."),
    config: str | None = typer.Option(None, "--config", "-c", help="TOML-Konfiguration."),
    out: str | None = typer.Option(None, "--out", "-o", help="Zielordner für die Ereignisse."),
    seconds: float | None = typer.Option(
        None, "--seconds", help="Nach so vielen Sekunden aufhören (nur mit Mikrofon)."
    ),
    lang: str = typer.Option("de", "--lang", help="Sprache der Meldungen: de oder en."),
) -> None:
    """Laufender Ton: gibt Ereignisse aus, während Ton ankommt."""
    import json

    from .adapters.source import iter_file, iter_mic
    from .stream import run_stream

    language = normalize_language(lang)
    try:
        settings = load_settings(Path(config) if config else None, lang=language)
    except (OSError, tomllib.TOMLDecodeError) as error:
        typer.echo(translate("error.generic", language, detail=str(error)))
        raise typer.Exit(code=1) from error

    run_config = settings.run
    if target:
        run_config = run_config.model_copy(update={"target_languages": list(target)})
    blocks: Iterator[np.ndarray]
    if source == "mic":
        live: Iterator[np.ndarray] = iter_mic()
        if seconds:
            limit = int(seconds / 0.5)
            blocks = itertools.islice(live, limit)
        else:
            blocks = live
    else:
        path = Path(source)
        if not path.is_file():
            typer.echo(translate("error.not_a_file", language, path=source))
            raise typer.Exit(code=1)
        blocks = iter_file(path)

    out_dir = Path(out) if out else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "ereignisse.jsonl"
    count = 0
    with events_path.open("w", encoding="utf-8") as handle:
        try:
            for event in run_stream(
                blocks, 16000, config=run_config, lang=language, translate=bool(target)
            ):
                count += 1
                line = {
                    "index": event.index,
                    "start_s": event.start_s,
                    "end_s": event.end_s,
                    "speaker": event.speaker,
                    "language": event.language,
                    "language_confidence": event.language_confidence,
                    "text": event.text,
                    "translations": event.translations,
                    "translated_from": event.translated_from,
                    "is_final": event.is_final,
                }
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
                handle.flush()
                stamp = f"[{event.start_s:6.2f}-{event.end_s:6.2f}]"
                typer.echo(f"{stamp} {event.speaker} {event.text}")
        except TranscriberError as error:
            typer.echo(error.localized(language))
            raise typer.Exit(code=error.exit_code) from error
    typer.echo(translate("cli.done", language, segments=count, speakers=1, languages=1))


@app.command()
def render(
    video: str = typer.Argument(..., help="Videodatei."),
    transcript: str = typer.Option(..., "--transcript", "-t", help="Transkript als JSON."),
    out: str = typer.Option(..., "--out", "-o", help="Zieldatei, z. B. untertitelt.mp4."),
    subtitle_lang: str | None = typer.Option(
        None, "--subtitle-lang", help="Sprache der Untertitel aus dem Transkript."
    ),
    adapter: str = typer.Option("ffmpeg", "--adapter", help="Renderer."),
    lang: str = typer.Option("de", "--lang", help="Sprache der Meldungen: de oder en."),
) -> None:
    """Brennt Untertitel aus einem Transkript in das Video ein."""
    import json

    language = normalize_language(lang)
    try:
        payload = json.loads(Path(transcript).read_text(encoding="utf-8"))
        parsed = Transcript.model_validate(payload)
    except (OSError, ValueError) as error:
        typer.echo(translate("error.generic", language, detail=str(error)))
        raise typer.Exit(code=1) from error

    renderer = DEFAULT_REGISTRY.create("video_renderer", adapter)
    try:
        written = renderer.render(Path(video), parsed, Path(out), subtitle_lang)
    except TranscriberError as error:
        typer.echo(error.localized(language))
        raise typer.Exit(code=error.exit_code) from error
    finally:
        release(renderer)
    typer.echo(translate("cli.video_written", language, path=written))


gallery_app = typer.Typer(add_completion=False, no_args_is_help=True, help="Galerie verwalten.")
app.add_typer(gallery_app, name="gallery")


def _gallery_adapter(adapter: str, path: str | None) -> object:
    options: dict[str, object] = {}
    if path:
        options["gallery"] = path
    return DEFAULT_REGISTRY.create("voiceprint", adapter, **options)


@gallery_app.command("enroll")
def gallery_enroll(
    path: str = typer.Argument(..., help="Audiodatei mit der Stimme."),
    name: str = typer.Option(..., "--name", "-n", help="Name der Person."),
    consent: bool = typer.Option(
        False, "--consent", help="Ausdrückliche Zustimmung zum Speichern des Stimmabdrucks."
    ),
    start: float = typer.Option(0.0, "--start", help="Beginn des Ausschnitts in Sekunden."),
    end: float | None = typer.Option(None, "--end", help="Ende des Ausschnitts in Sekunden."),
    gallery: str | None = typer.Option(None, "--gallery", help="Pfad der Galerie-Datei."),
    adapter: str = typer.Option(
        DEFAULT_ADAPTERS["voiceprint"], "--adapter", help="Adapter für den Stimmabdruck."
    ),
    lang: str = typer.Option("de", "--lang", help="Sprache der Meldungen: de oder en."),
) -> None:
    """Meldet eine Person an. Ohne --consent wird nichts gespeichert (Spezifikation 7)."""
    language = normalize_language(lang)
    source = Path(path)
    if not source.is_file():
        typer.echo(translate("error.not_a_file", language, path=path))
        raise typer.Exit(code=1)
    if not consent:
        typer.echo(translate("error.gallery_consent", language, name=name))
        raise typer.Exit(code=2)
    voiceprint = _gallery_adapter(adapter, gallery)
    try:
        end_s = end if end is not None else float(probe(source).duration_s)
        person = voiceprint.enroll(source, start, end_s, name, consent=consent)  # type: ignore[attr-defined]
    except TranscriberError as error:
        typer.echo(error.localized(language))
        raise typer.Exit(code=error.exit_code) from error
    finally:
        release(voiceprint)
    typer.echo(
        translate(
            "cli.enrolled",
            language,
            name=person.name,
            person_id=person.person_id,
            samples=person.samples,
        )
    )


@gallery_app.command("list")
def gallery_list(
    gallery: str | None = typer.Option(None, "--gallery", help="Pfad der Galerie-Datei."),
    adapter: str = typer.Option(DEFAULT_ADAPTERS["voiceprint"], "--adapter"),
    lang: str = typer.Option("de", "--lang"),
) -> None:
    """Zeigt die gespeicherten Personen."""
    language = normalize_language(lang)
    voiceprint = _gallery_adapter(adapter, gallery)
    try:
        people = list(voiceprint.people())  # type: ignore[attr-defined]
    finally:
        release(voiceprint)
    if not people:
        typer.echo(translate("cli.gallery_empty", language))
        return
    typer.echo(translate("cli.gallery_list", language, count=len(people)))
    for person in people:
        typer.echo(
            translate(
                "cli.gallery_row",
                language,
                name=person.name,
                samples=person.samples,
                created_at=person.created_at,
            )
        )


@gallery_app.command("delete")
def gallery_delete(
    reference: str = typer.Argument(..., help="Name oder Kennung der Person."),
    gallery: str | None = typer.Option(None, "--gallery", help="Pfad der Galerie-Datei."),
    adapter: str = typer.Option(DEFAULT_ADAPTERS["voiceprint"], "--adapter"),
    lang: str = typer.Option("de", "--lang"),
) -> None:
    """Löscht eine Person samt Stimmabdrücken."""
    language = normalize_language(lang)
    voiceprint = _gallery_adapter(adapter, gallery)
    try:
        count = int(voiceprint.delete(reference))  # type: ignore[attr-defined]
    except TranscriberError as error:
        typer.echo(error.localized(language))
        raise typer.Exit(code=error.exit_code) from error
    finally:
        release(voiceprint)
    typer.echo(translate("cli.deleted", language, count=count))


def main() -> None:  # pragma: no cover - Einstiegspunkt
    sys.exit(app())
