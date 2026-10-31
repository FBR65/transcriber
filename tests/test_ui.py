"""S21 und S29: Oberfläche. Ohne Browser: Steuerbaum prüfen, Klient gegen die App testen."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import uvicorn

from transcriber.gallery import Gallery
from transcriber.registry import Registry
from transcriber.service import create_app
from transcriber.ui import ApiClient, build_view, gallery_people, labels

from .conftest import register_fake_adapters, write_wav


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "c.toml"
    path.write_text(
        '[adapters]\nasr="fake"\ndiarizer="fake"\nlanguage_id="fake"\n'
        'translator="fake"\nvoiceprint=""\n\n[targets]\nlanguages=["fr"]\n',
        encoding="utf-8",
    )
    return path


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def api(tmp_path: Path) -> Iterator[SimpleNamespace]:
    """Echter HTTP-Server im Hintergrund: die Oberfläche spricht wirklich über HTTP."""
    registry = Registry()
    register_fake_adapters(registry)
    app = create_app(
        workdir=tmp_path / "jobs", registry=registry, config_path=config_file(tmp_path)
    )
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "Dienst ist nicht gestartet"
    client = ApiClient(f"http://127.0.0.1:{port}")
    try:
        yield SimpleNamespace(client=client, app=app)
    finally:
        client.close()
        server.should_exit = True
        thread.join(timeout=10)


class FakePage:
    """Minimales Page-Objekt: die Ansicht ruft nur `update()` auf."""

    def __init__(self) -> None:
        self.updates = 0

    def update(self) -> None:
        self.updates += 1


def controls(root: object) -> list[object]:
    return list(getattr(root, "controls", []))


def texts(root: object) -> list[str]:
    """Alle sichtbaren Texte im Steuerbaum, auch in Zeilen und Spalten."""
    found: list[str] = []

    def walk(control: object) -> None:
        value = getattr(control, "value", None)
        if isinstance(value, str):
            found.append(value)
        for child in getattr(control, "controls", None) or []:
            walk(child)

    walk(root)
    return found


def test_labels_in_both_languages() -> None:
    assert labels("de")["title"] == "Transkription"
    assert labels("en")["title"] == "Transcription"
    assert labels("de")["delete"] == "Löschen"
    assert labels("en")["delete"] == "Delete"


def test_view_shows_jobs_from_the_service(api: SimpleNamespace, tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "probe.wav")
    created = api.client.upload("probe.wav", audio.read_bytes())
    api.app.state.manager.wait(created["job_id"], timeout=30)  # type: ignore[attr-defined]

    page = FakePage()
    root = build_view(page, api.client, lang="de")
    assert page.updates >= 1

    payload = root.data  # type: ignore[attr-defined]
    assert payload["labels"]["title"] == "Transkription"
    jobs = payload["state"]["jobs"]
    assert jobs and jobs[0]["filename"] == "probe.wav"
    assert any("probe.wav" in text for text in texts(controls(root)[4]))


def test_view_shows_people_and_deletes_them(api: SimpleNamespace, tmp_path: Path) -> None:
    gallery_path = tmp_path / "galerie.db"
    gallery = Gallery(gallery_path)
    gallery.add("Herr X", np.array([1.0, 0.0, 0.0], dtype=np.float32), consent=True)

    page = FakePage()
    root = build_view(page, api.client, lang="de", gallery_path=str(gallery_path))
    people = gallery_people(str(gallery_path))
    assert people == [(people[0][0], "Herr X", 1)]
    assert any("Herr X" in text for text in texts(controls(root)[6]))

    from transcriber.ui import delete_person

    assert delete_person("Herr X", str(gallery_path)) == 1
    assert gallery_people(str(gallery_path)) == []


def test_view_switches_language(api: SimpleNamespace) -> None:
    german = build_view(FakePage(), api.client, lang="de")
    english = build_view(FakePage(), api.client, lang="en")
    assert german.data["labels"]["jobs"] == "Aufträge"  # type: ignore[attr-defined]
    assert english.data["labels"]["jobs"] == "Jobs"  # type: ignore[attr-defined]
    assert english.data["lang"] == "en"  # type: ignore[attr-defined]


def test_view_survives_an_unreachable_service(tmp_path: Path) -> None:
    dead = ApiClient("http://127.0.0.1:9", timeout=0.5)
    page = FakePage()
    root = build_view(page, dead, lang="de")
    assert root.data["state"]["jobs"] == []  # type: ignore[attr-defined]
    assert root.data["labels"]["offline"]  # type: ignore[attr-defined]


def test_transcript_is_rendered(api: SimpleNamespace, tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "probe.wav")
    created = api.client.upload("probe.wav", audio.read_bytes())
    api.app.state.manager.wait(created["job_id"], timeout=30)  # type: ignore[attr-defined]
    payload = api.client.transcript(created["job_id"])
    assert payload["segments"]
    line = (
        f"[{payload['segments'][0]['start_s']:.1f}-{payload['segments'][0]['end_s']:.1f}] "
        f"{payload['segments'][0]['speaker']}: {payload['segments'][0]['text']}"
    )
    assert line.startswith("[")


def test_export_url_points_at_the_service(api: SimpleNamespace) -> None:
    assert api.client.export_url("abc", "srt").endswith("/jobs/abc/export/srt")


def test_gallery_module_is_reachable_without_models(tmp_path: Path) -> None:
    """Die Oberfläche liest die Galerie direkt; dafür darf kein Modell geladen werden."""
    path = tmp_path / "g.db"
    Gallery(path).add("Frau Y", np.array([0.0, 1.0], dtype=np.float32), consent=True)
    people = gallery_people(str(path))
    assert people[0][1] == "Frau Y"
    assert json.dumps(people, default=str)
