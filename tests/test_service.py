"""S23–S26: HTTP-Dienst. TestClient statt echtem Netz, echte Dateien, Test-Adapter."""

from __future__ import annotations

import socket
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from transcriber.registry import Registry
from transcriber.service import create_app

from .conftest import register_fake_adapters, write_wav


def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "c.toml"
    path.write_text(
        '[adapters]\nasr="fake"\ndiarizer="fake"\nlanguage_id="fake"\n'
        'translator="fake"\nvoiceprint=""\n\n[targets]\nlanguages=["fr"]\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    registry = Registry()
    register_fake_adapters(registry)
    app = create_app(
        workdir=tmp_path / "jobs", registry=registry, config_path=config_file(tmp_path)
    )
    return TestClient(app)


def upload(client: TestClient, path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        response = client.post("/jobs", files={"file": (path.name, handle, "audio/wav")})
    assert response.status_code == 202, response.text
    return dict(response.json())


def wait_done(client: TestClient, job_id: str, timeout: float = 30.0) -> dict[str, object]:
    manager = client.app.state.manager
    job = manager.wait(job_id, timeout=timeout)
    return {"job_id": job.job_id, "state": job.state, "error": job.error}


def test_job_roundtrip(client: TestClient, tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "probe.wav")
    created = upload(client, audio)
    assert created["state"] in {"queued", "running", "done"}
    job_id = str(created["job_id"])

    state = wait_done(client, job_id)
    assert state["state"] == "done", state

    payload = client.get(f"/jobs/{job_id}/transcript").json()
    assert payload["schema_version"] == 1
    assert payload["segments"]
    assert payload["segments"][0]["translations"]

    exported = client.get(f"/jobs/{job_id}/export/srt")
    assert exported.status_code == 200
    assert "-->" in exported.text

    listing = client.get("/jobs").json()
    assert any(entry["job_id"] == job_id for entry in listing)

    assert client.delete(f"/jobs/{job_id}").status_code == 204
    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_corrupt_upload_fails_without_killing_the_service(
    client: TestClient, tmp_path: Path
) -> None:
    broken = tmp_path / "kaputt.wav"
    broken.write_text("kein Ton", encoding="utf-8")
    created = upload(client, broken)
    job_id = str(created["job_id"])
    state = wait_done(client, job_id)
    assert state["state"] == "failed"
    assert state["error"]
    assert client.get(f"/jobs/{job_id}/transcript").status_code == 409

    # Der Dienst lebt weiter und ein guter Auftrag geht danach durch.
    good = write_wav(tmp_path / "gut.wav")
    second = upload(client, good)
    assert wait_done(client, str(second["job_id"]))["state"] == "done"


def test_unsupported_file_type_is_rejected(client: TestClient, tmp_path: Path) -> None:
    document = tmp_path / "text.txt"
    document.write_text("nichts", encoding="utf-8")
    with document.open("rb") as handle:
        response = client.post("/jobs", files={"file": ("text.txt", handle, "text/plain")})
    assert response.status_code == 422
    assert "unsupported" in response.json()["detail"]


def test_empty_upload_is_rejected(client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "leer.wav"
    empty.write_bytes(b"")
    with empty.open("rb") as handle:
        response = client.post("/jobs", files={"file": ("leer.wav", handle, "audio/wav")})
    assert response.status_code == 422


def test_unknown_job_and_unknown_format(client: TestClient) -> None:
    assert client.get("/jobs/gibtsnicht").status_code == 404
    assert client.delete("/jobs/gibtsnicht").status_code == 404
    assert client.get("/jobs/gibtsnicht/transcript").status_code == 404


def test_openapi_lists_the_documented_paths(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert {
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/transcript",
        "/jobs/{job_id}/export/{fmt}",
    } <= paths
    assert schema["info"]["title"] == "transcriber"


def test_stream_socket_delivers_events(client: TestClient, tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "strom.wav", seconds=2.0, rate=16000)
    raw = np.frombuffer((audio.read_bytes()), dtype=np.int16)
    with client.websocket_connect("/stream") as socket_conn:
        socket_conn.send_bytes(raw.astype("<f4").tobytes())
        socket_conn.send_bytes(b"")  # Ende des Tons
        payload = socket_conn.receive_json()
    assert payload["is_final"] is True
    assert payload["text"].strip()


def test_service_defaults_to_localhost() -> None:
    """S26: ohne --host bindet der Dienst nur an 127.0.0.1."""
    import inspect

    from transcriber import cli as cli_module
    from transcriber.service import serve

    parameters = inspect.signature(serve).parameters
    assert parameters["host"].default == "127.0.0.1"
    cli_parameters = inspect.signature(cli_module.serve).parameters
    assert cli_parameters["host"].default.default == "127.0.0.1"
    assert socket.gethostbyname("127.0.0.1") == "127.0.0.1"


def test_job_export_rejects_unknown_format(client: TestClient, tmp_path: Path) -> None:
    audio = write_wav(tmp_path / "probe.wav")
    job_id = str(upload(client, audio)["job_id"])
    wait_done(client, job_id)
    assert client.get(f"/jobs/{job_id}/export/docx").status_code == 422
