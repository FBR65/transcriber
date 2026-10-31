"""Galerie der Stimmabdrücke. Lokale SQLite-Datei, kein ML-Code, kein Netzwerk.

Regeln aus SPEC Abschnitt 7:
- Anmeldung nur mit ausdrücklicher Zustimmung.
- Löschen entfernt den Datensatz vollständig (`PRAGMA secure_delete`, danach `VACUUM`).
- Datei gehört dem Nutzer, Rechte 600.
- Gleichzeitiger Zugriff wird über eine Sperrdatei geordnet (S22).
"""

from __future__ import annotations

import contextlib
import fcntl
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .errors import GalleryConsentError, PersonNotFoundError
from .ports import PersonInfo, VoiceprintMatch

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consent_at TEXT NOT NULL,
    model TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voiceprint (
    print_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    vector BLOB NOT NULL,
    dim INTEGER NOT NULL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS voiceprint_person ON voiceprint(person_id);
CREATE UNIQUE INDEX IF NOT EXISTS person_name ON person(name);
"""


def default_gallery_path() -> Path:
    return Path.home() / ".local" / "share" / "transcriber" / "gallery.db"


def cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    a = first.astype(np.float32, copy=False).reshape(-1)
    b = second.astype(np.float32, copy=False).reshape(-1)
    if a.size != b.size or a.size == 0:
        raise ValueError("embeddings must have the same non-zero length")
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


class Gallery:
    """Stimmabdrücke mit Namen. Alle Schreibvorgänge sind gesperrt und transaktional."""

    def __init__(self, path: str | Path | None = None, threshold: float = 0.70) -> None:
        self.path = Path(path) if path is not None else default_gallery_path()
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self.threshold = threshold

    # --- Verbindung -------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):  # Rechte sind eine Härtung, kein Muss
            self.path.parent.chmod(0o700)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        connection.executescript(SCHEMA)
        if not self.path.exists():  # pragma: no cover - von sqlite angelegt
            self.path.touch()
        with contextlib.suppress(OSError):  # Rechte sind eine Härtung, kein Muss
            self.path.chmod(0o600)
        return connection

    @contextmanager
    def _locked(self, exclusive: bool) -> Iterator[sqlite3.Connection]:
        """Sperrt die Datei prozessübergreifend. Schreiben exklusiv, Lesen geteilt."""
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            connection = self._connect()
            try:
                yield connection
                if exclusive:
                    connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    # --- Lesen ------------------------------------------------------------

    def people(self) -> list[PersonInfo]:
        with self._locked(exclusive=False) as connection:
            rows = connection.execute(
                """
                SELECT p.person_id, p.name, p.created_at, COUNT(v.print_id) AS samples
                FROM person p LEFT JOIN voiceprint v ON v.person_id = p.person_id
                GROUP BY p.person_id ORDER BY p.created_at, p.name
                """
            ).fetchall()
        return [
            PersonInfo(
                person_id=row["person_id"],
                name=row["name"],
                created_at=row["created_at"],
                samples=int(row["samples"]),
            )
            for row in rows
        ]

    def match(self, embedding: np.ndarray) -> VoiceprintMatch | None:
        """Bester Treffer über der Schwelle, oder None."""
        with self._locked(exclusive=False) as connection:
            rows = connection.execute(
                "SELECT p.person_id, p.name, v.vector, v.dim FROM voiceprint v "
                "JOIN person p ON p.person_id = v.person_id"
            ).fetchall()
        best: VoiceprintMatch | None = None
        for row in rows:
            stored = np.frombuffer(row["vector"], dtype=np.float32).reshape(int(row["dim"]))
            if stored.size != np.asarray(embedding).size:
                continue
            similarity = cosine_similarity(embedding, stored)
            if similarity < self.threshold:
                continue
            if best is None or similarity > best.similarity:
                best = VoiceprintMatch(
                    person_id=str(row["person_id"]),
                    name=str(row["name"]),
                    similarity=similarity,
                )
        return best

    # --- Schreiben --------------------------------------------------------

    def add(
        self,
        name: str,
        embedding: np.ndarray,
        *,
        consent: bool,
        source: str = "",
        model: str = "",
    ) -> PersonInfo:
        if not consent:
            raise GalleryConsentError(name)
        clean = name.strip()
        if not clean:
            raise ValueError("name must not be empty")
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if vector.size == 0:
            raise ValueError("embedding must not be empty")
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        with self._locked(exclusive=True) as connection:
            # Der eindeutige Index auf `name` macht die Anmeldung unabhängig von der Sperre
            # korrekt: zwei Prozesse können keine zwei Personen mit gleichem Namen anlegen.
            connection.execute(
                "INSERT OR IGNORE INTO person (person_id, name, created_at, consent_at, model) "
                "VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, clean, now, now, model),
            )
            row = connection.execute(
                "SELECT person_id FROM person WHERE name = ?", (clean,)
            ).fetchone()
            if row is None:  # pragma: no cover - nach INSERT OR IGNORE unerreichbar
                raise RuntimeError("person could not be stored")
            person_id = str(row["person_id"])
            connection.execute(
                "INSERT INTO voiceprint (person_id, vector, dim, source) VALUES (?, ?, ?, ?)",
                (person_id, vector.tobytes(), int(vector.size), source),
            )
            samples = connection.execute(
                "SELECT COUNT(*) AS n FROM voiceprint WHERE person_id = ?", (person_id,)
            ).fetchone()["n"]
        return PersonInfo(
            person_id=person_id, name=clean, created_at=now, samples=int(samples)
        )

    def delete(self, reference: str) -> int:
        """Löscht eine Person nach Kennung oder Name. Gibt die Zahl der Treffer zurück."""
        key = reference.strip()
        if not key:
            raise ValueError("reference must not be empty")
        with self._locked(exclusive=True) as connection:
            rows = connection.execute(
                "SELECT person_id FROM person WHERE person_id = ? OR name = ?", (key, key)
            ).fetchall()
            if not rows:
                raise PersonNotFoundError(key)
            for row in rows:
                person_id = row["person_id"]
                connection.execute("DELETE FROM voiceprint WHERE person_id = ?", (person_id,))
                connection.execute("DELETE FROM person WHERE person_id = ?", (person_id,))
        self._compact()
        return len(rows)

    def _compact(self) -> None:
        """Schreibt die Datei neu, damit gelöschte Daten nicht als Rest in der Datei bleiben."""
        with self._locked(exclusive=True) as connection:
            connection.execute("VACUUM")
