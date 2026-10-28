"""Kommandozeile. Alle Meldungen über i18n, Standard Deutsch."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import typer

from .audio import AUDIO_SUFFIXES
from .config import load_settings
from .core import run_file
from .errors import TranscriberError
from .exporters import EXPORTERS, export
from .i18n import normalize_language, translate
from .licensing import LICENCES
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


def main() -> None:  # pragma: no cover - Einstiegspunkt
    sys.exit(app())
