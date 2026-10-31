"""HTTP-Schnittstelle nach SPEC 3.1. Keine Fachlogik, nur Aufträge um den Kern herum.

Der Dienst bindet ohne `--host` nur an 127.0.0.1 (S26). Modelle werden erst beim ersten Auftrag
geladen, nicht beim Start.
"""

from __future__ import annotations

import asyncio
import queue
import shutil
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .config import load_settings
from .core import run_file
from .errors import TranscriberError
from .exporters import EXPORTERS, export
from .models import RunConfig, Transcript
from .registry import DEFAULT_REGISTRY, Registry

State = Literal["queued", "running", "done", "failed"]
SUFFIX_ALLOWED = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".mp4", ".webm", ".opus"}


@dataclass(slots=True)
class Job:
    job_id: str
    filename: str
    state: State = "queued"
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    transcript: Transcript | None = None
    files: list[Path] = field(default_factory=list)


class JobManager:
    """Führt Aufträge nacheinander aus. Ein Arbeitsthread, weil die GPU ohnehin seriell ist."""

    def __init__(self, workdir: Path, registry: Registry, run_config: RunConfig) -> None:
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.run_config = run_config
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    # --- API für die Endpunkte -------------------------------------------

    def submit(self, filename: str, data: bytes) -> Job:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUFFIX_ALLOWED:
            raise ValueError(f"unsupported file type: {suffix or 'ohne Endung'}")
        job_id = uuid.uuid4().hex
        job_dir = self.workdir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        source = job_dir / f"quelle{suffix}"
        source.write_bytes(data)
        job = Job(job_id=job_id, filename=filename)
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at)

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        with self._lock:
            self._jobs.pop(job_id, None)
        for path in job.files:
            path.unlink(missing_ok=True)
        shutil.rmtree(self.workdir / job_id, ignore_errors=True)

    def wait(self, job_id: str, timeout: float = 60.0) -> Job:
        """Nur für Tests und einfache Aufrufer: wartet, bis der Auftrag fertig ist."""
        deadline = threading.Event()
        waited = 0.0
        while waited < timeout:
            job = self.get(job_id)
            if job.state in {"done", "failed"}:
                return job
            deadline.wait(0.05)
            waited += 0.05
        return self.get(job_id)

    # --- Arbeitsthread --------------------------------------------------

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get(job_id)
            job.state = "running"
            try:
                source = self.workdir / job_id / f"quelle{Path(job.filename).suffix.lower()}"
                transcript = run_file(source, config=self.run_config, registry=self.registry)
                job.transcript = transcript
                job.files = export(transcript, self.workdir / job_id, formats=("json",))
                job.state = "done"
            except TranscriberError as error:
                job.state = "failed"
                job.error = error.localized("de")
            except Exception as error:  # noqa: BLE001 - der Dienst darf nicht sterben
                job.state = "failed"
                job.error = f"{type(error).__name__}: {error}"


class JobOut(BaseModel):
    job_id: str
    filename: str
    state: State
    error: str | None = None
    created_at: str


def _job_out(job: Job) -> JobOut:
    return JobOut(
        job_id=job.job_id,
        filename=job.filename,
        state=job.state,
        error=job.error,
        created_at=job.created_at,
    )


def create_app(
    *,
    workdir: Path | None = None,
    registry: Registry | None = None,
    config_path: Path | None = None,
) -> FastAPI:
    """Baut die App. Ohne Argumente gelten Arbeitsordner in /tmp und die Standardadapter."""
    settings = load_settings(config_path)
    manager = JobManager(
        workdir or Path.home() / ".cache" / "transcriber" / "jobs",
        registry or DEFAULT_REGISTRY,
        settings.run,
    )

    app = FastAPI(title="transcriber", version="0.1.0")
    app.state.manager = manager

    @app.post("/jobs", response_model=JobOut, status_code=202)
    def create_job(file: UploadFile = File(...)) -> JobOut:
        data = file.file.read()
        if not data:
            raise HTTPException(status_code=422, detail="empty upload")
        try:
            job = manager.submit(file.filename or "upload.wav", data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return _job_out(job)

    @app.get("/jobs", response_model=list[JobOut])
    def list_jobs() -> list[JobOut]:
        return [_job_out(job) for job in manager.list()]

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def job_state(job_id: str) -> JobOut:
        try:
            return _job_out(manager.get(job_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown job") from error

    @app.get("/jobs/{job_id}/transcript")
    def job_transcript(job_id: str) -> JSONResponse:
        try:
            job = manager.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown job") from error
        if job.transcript is None:
            raise HTTPException(status_code=409, detail=f"job is {job.state}")
        return JSONResponse(job.transcript.to_dict())

    @app.get("/jobs/{job_id}/export/{fmt}")
    def job_export(job_id: str, fmt: str) -> FileResponse:
        if fmt not in EXPORTERS:
            raise HTTPException(status_code=422, detail=f"unknown format: {fmt}")
        try:
            job = manager.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown job") from error
        if job.transcript is None:
            raise HTTPException(status_code=409, detail=f"job is {job.state}")
        written = export(job.transcript, manager.workdir / job_id, formats=(fmt,))
        return FileResponse(written[0], filename=written[0].name)

    @app.delete("/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> None:
        try:
            manager.delete(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown job") from error

    @app.websocket("/stream")
    async def stream_socket(websocket: WebSocket) -> None:
        """Ton als rohe float32-Blöcke (16 kHz mono) hinein, Ereignisse als JSON heraus."""
        from .stream import run_stream

        await websocket.accept()
        inbox: queue.Queue[bytes | None] = queue.Queue()
        outbox: queue.Queue[dict[str, object] | None] = queue.Queue()

        def blocks() -> Iterator[np.ndarray]:
            while True:
                chunk = inbox.get()
                if chunk is None:
                    return
                if chunk:
                    yield np.frombuffer(chunk, dtype=np.float32)

        def worker() -> None:
            try:
                for event in run_stream(
                    blocks(),
                    16000,
                    config=manager.run_config,
                    registry=manager.registry,
                    translate=False,
                ):
                    outbox.put(
                        {
                            "index": event.index,
                            "start_s": event.start_s,
                            "end_s": event.end_s,
                            "speaker": event.speaker,
                            "language": event.language,
                            "text": event.text,
                            "is_final": event.is_final,
                        }
                    )
            finally:
                outbox.put(None)

        threading.Thread(target=worker, daemon=True).start()

        async def pump_to_worker() -> None:
            """Leere Nachricht bedeutet: Ende des Tons."""
            try:
                while True:
                    chunk = await websocket.receive_bytes()
                    inbox.put(chunk if chunk else None)
                    if not chunk:
                        return
            except WebSocketDisconnect:
                inbox.put(None)
            except Exception:  # noqa: BLE001 - Verbindung beendet
                inbox.put(None)

        reader = asyncio.create_task(pump_to_worker())
        try:
            while True:
                payload = await asyncio.to_thread(outbox.get)
                if payload is None:
                    break
                await websocket.send_json(payload)
        finally:
            reader.cancel()

    return app


def serve(host: str = "127.0.0.1", port: int = 8000, config_path: Path | None = None) -> Any:
    """Startet den Dienst. Ohne `host` nur lokal (S26)."""
    import uvicorn

    app = create_app(config_path=config_path)
    return uvicorn.run(app, host=host, port=port, log_level="info")


__all__ = ["Job", "JobManager", "create_app", "serve"]
