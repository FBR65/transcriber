"""Oberfläche mit Flet (SPEC D13 = b). Sie spricht mit dem HTTP-Dienst aus P5.

Die Oberfläche enthält keine Fachlogik: Aufträge anlegen, Zustand anzeigen, Transkript lesen,
Personen der Galerie anzeigen und löschen. Texte kommen aus den Sprachkatalogen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .i18n import normalize_language, translate


@dataclass(slots=True)
class ApiClient:
    """Dünner Klient um den Dienst. Alles, was die Oberfläche braucht."""

    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 30.0
    _client: httpx.Client | None = field(default=None, repr=False)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def list_jobs(self) -> list[dict[str, Any]]:
        response = self.client.get("/jobs")
        response.raise_for_status()
        return list(response.json())

    def upload(self, name: str, data: bytes) -> dict[str, Any]:
        files = {"file": (name, data, "application/octet-stream")}
        response = self.client.post("/jobs", files=files)
        response.raise_for_status()
        return dict(response.json())

    def job(self, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        return dict(response.json())

    def transcript(self, job_id: str) -> dict[str, Any]:
        response = self.client.get(f"/jobs/{job_id}/transcript")
        response.raise_for_status()
        return dict(response.json())

    def delete_job(self, job_id: str) -> None:
        response = self.client.delete(f"/jobs/{job_id}")
        response.raise_for_status()

    def export_url(self, job_id: str, fmt: str = "srt") -> str:
        return f"{self.base_url}/jobs/{job_id}/export/{fmt}"

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def gallery_people(gallery_path: str | None = None) -> list[tuple[str, str, int]]:
    """Personen aus der lokalen Galerie: (Kennung, Name, Zahl der Stimmabdrücke)."""
    from .gallery import Gallery

    return [
        (person.person_id, person.name, person.samples)
        for person in Gallery(gallery_path).people()
    ]


def delete_person(reference: str, gallery_path: str | None = None) -> int:
    from .gallery import Gallery

    return Gallery(gallery_path).delete(reference)


def labels(lang: str) -> dict[str, str]:
    language = normalize_language(lang)
    keys = {
        "title": "ui.title",
        "upload": "ui.upload",
        "refresh": "ui.refresh",
        "jobs": "ui.jobs",
        "people": "ui.people",
        "delete": "ui.delete",
        "transcript": "ui.transcript",
        "empty": "ui.empty",
        "language": "ui.language",
        "offline": "ui.offline",
    }
    return {name: translate(key, language) for name, key in keys.items()}


def build_view(
    page: Any,
    client: ApiClient,
    lang: str = "de",
    gallery_path: str | None = None,
    on_upload: Callable[[bytes, str], dict[str, Any]] | None = None,
) -> Any:
    """Baut die Ansicht. Gibt das Wurzel-Steuerelement zurück (für Prüfungen ohne Browser)."""
    import flet as ft

    text = labels(lang)
    state: dict[str, Any] = {"jobs": [], "people": []}

    jobs_list = ft.Column(spacing=4)
    people_list = ft.Column(spacing=4)
    status = ft.Text("")
    transcript_box = ft.Text("", selectable=True)

    def refresh(_event: object | None = None) -> None:
        try:
            state["jobs"] = client.list_jobs()
        except httpx.HTTPError:
            status.value = text["offline"]
            state["jobs"] = []
        jobs_list.controls.clear()
        if not state["jobs"]:
            jobs_list.controls.append(ft.Text(text["empty"]))
        for job in state["jobs"]:
            jobs_list.controls.append(
                ft.Row(
                    controls=[
                        ft.Text(f"{job['filename']} — {job['state']}", width=380),
                        ft.TextButton(
                            text["transcript"],
                            on_click=lambda event, job_id=job["job_id"]: show_transcript(job_id),
                        ),
                    ]
                )
            )
        try:
            state["people"] = gallery_people(gallery_path)
        except Exception:  # noqa: BLE001 - leere oder fehlende Galerie ist kein Fehler
            state["people"] = []
        people_list.controls.clear()
        if not state["people"]:
            people_list.controls.append(ft.Text(text["empty"]))
        for _person_id, name, samples in state["people"]:
            people_list.controls.append(
                ft.Row(
                    controls=[
                        ft.Text(f"{name} ({samples})", width=380),
                        ft.TextButton(
                            text["delete"],
                            on_click=lambda event, reference=name: delete_and_refresh(reference),
                        ),
                    ]
                )
            )
        page.update()

    def show_transcript(job_id: str) -> None:
        try:
            payload = client.transcript(job_id)
        except httpx.HTTPError:
            transcript_box.value = text["offline"]
        else:
            lines = [
                f"[{segment['start_s']:.1f}-{segment['end_s']:.1f}] "
                f"{segment['speaker']}: {segment['text']}"
                for segment in payload.get("segments", [])
            ]
            transcript_box.value = "\n".join(lines)
        page.update()

    def delete_and_refresh(reference: str) -> None:
        try:
            delete_person(reference, gallery_path)
        finally:
            refresh(None)

    def handle_upload(_event: object | None = None) -> None:
        if on_upload is None:
            return
        try:
            created = on_upload(b"", "upload")
        except Exception:  # noqa: BLE001 - Oberfläche darf nicht abstürzen
            status.value = text["offline"]
        else:
            status.value = f"{created.get('filename', '')}: {created.get('state', '')}"
        refresh(None)

    upload_button = ft.Button(text["upload"], on_click=handle_upload)
    refresh_button = ft.Button(text["refresh"], on_click=refresh)

    language_switch = ft.Dropdown(
        label=text["language"],
        value=normalize_language(lang),
        options=[ft.dropdown.Option("de", "Deutsch"), ft.dropdown.Option("en", "English")],
    )

    root = ft.Column(
        controls=[
            ft.Text(text["title"], size=22, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[upload_button, refresh_button, language_switch]),
            status,
            ft.Text(text["jobs"], weight=ft.FontWeight.BOLD),
            jobs_list,
            ft.Text(text["people"], weight=ft.FontWeight.BOLD),
            people_list,
            transcript_box,
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
    )
    root.data = {"labels": text, "lang": normalize_language(lang), "state": state}
    refresh(None)
    return root


def run_ui(
    api: str = "http://127.0.0.1:8000",
    port: int = 8550,
    lang: str = "de",
    gallery_path: str | None = None,
    host: str = "127.0.0.1",
) -> None:
    """Startet die Oberfläche im Web-Modus."""
    import flet as ft

    client = ApiClient(api)

    def main(page: ft.Page) -> None:
        page.title = labels(lang)["title"]
        page.add(build_view(page, client, lang=lang, gallery_path=gallery_path))

    ft.run(main, view=ft.AppView.WEB_BROWSER, host=host, port=port)


__all__ = ["ApiClient", "build_view", "delete_person", "gallery_people", "labels", "run_ui"]
