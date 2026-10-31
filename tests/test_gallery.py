"""S16-S19, S22 auf Ebene der Galerie. Ohne Modelle, ohne Netz."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import numpy as np
import pytest

from transcriber.errors import GalleryConsentError, PersonNotFoundError
from transcriber.gallery import Gallery, cosine_similarity


def vector(seed: int, dim: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = rng.normal(size=dim).astype(np.float32)
    return values / np.linalg.norm(values)


@pytest.fixture
def gallery(tmp_path: Path) -> Gallery:
    return Gallery(tmp_path / "galerie" / "gallery.db", threshold=0.9)


def test_cosine_similarity_bounds() -> None:
    a = vector(1)
    assert cosine_similarity(a, a) == pytest.approx(1.0, abs=1e-6)
    assert cosine_similarity(a, -a) == pytest.approx(-1.0, abs=1e-6)
    with pytest.raises(ValueError):
        cosine_similarity(a, vector(2, dim=4))
    with pytest.raises(ValueError):
        cosine_similarity(np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32))


def test_enroll_requires_consent(gallery: Gallery) -> None:
    with pytest.raises(GalleryConsentError) as error:
        gallery.add("Herr X", vector(1), consent=False)
    assert error.value.exit_code == 2
    assert gallery.people() == []
    assert not gallery.path.exists() or gallery.path.stat().st_size >= 0


def test_enroll_and_match(gallery: Gallery) -> None:
    person = gallery.add("Herr X", vector(1), consent=True)
    assert person.name == "Herr X"
    assert person.samples == 1
    assert [entry.name for entry in gallery.people()] == ["Herr X"]

    match = gallery.match(vector(1))
    assert match is not None
    assert match.name == "Herr X"
    assert match.similarity == pytest.approx(1.0, abs=1e-5)


def test_match_respects_threshold(gallery: Gallery) -> None:
    gallery.add("Herr X", vector(1), consent=True)
    noise = vector(1) + 0.9 * vector(7)
    assert gallery.match(noise) is None


def test_second_sample_joins_person(gallery: Gallery) -> None:
    gallery.add("Herr X", vector(1), consent=True)
    second = gallery.add("Herr X", vector(2), consent=True)
    assert second.samples == 2
    assert len(gallery.people()) == 1


def test_delete_by_name_removes_prints(gallery: Gallery) -> None:
    gallery.add("Herr X", vector(1), consent=True)
    gallery.add("Frau Y", vector(3), consent=True)
    assert gallery.delete("Herr X") == 1
    assert [entry.name for entry in gallery.people()] == ["Frau Y"]
    assert gallery.match(vector(1)) is None
    blob = gallery.path.read_bytes()
    assert b"Herr X" not in blob, "Name steht noch in der Datei"


def test_delete_removes_prints_from_the_file(gallery: Gallery) -> None:
    import sqlite3

    gallery.add("Herr X", vector(1), consent=True)
    gallery.delete("Herr X")
    connection = sqlite3.connect(gallery.path)
    try:
        prints = connection.execute("SELECT COUNT(*) FROM voiceprint").fetchone()[0]
        persons = connection.execute("SELECT COUNT(*) FROM person").fetchone()[0]
    finally:
        connection.close()
    assert prints == 0, "Stimmabdruck blieb in der Datenbank"
    assert persons == 0


def test_delete_by_id(gallery: Gallery) -> None:
    person = gallery.add("Frau Y", vector(3), consent=True)
    assert gallery.delete(person.person_id) == 1
    assert gallery.people() == []


def test_delete_unknown_person(gallery: Gallery) -> None:
    with pytest.raises(PersonNotFoundError):
        gallery.delete("gibt-es-nicht")


def test_gallery_file_is_private(gallery: Gallery) -> None:
    gallery.add("Herr X", vector(1), consent=True)
    mode = gallery.path.stat().st_mode & 0o777
    assert mode == 0o600


def test_empty_name_is_rejected(gallery: Gallery) -> None:
    with pytest.raises(ValueError):
        gallery.add("   ", vector(1), consent=True)


def test_threshold_must_be_sane(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Gallery(tmp_path / "x.db", threshold=0.0)
    with pytest.raises(ValueError):
        Gallery(tmp_path / "x.db", threshold=1.5)


def _writer(path: str, seed: int) -> None:
    gallery = Gallery(path, threshold=0.9)
    for index in range(20):
        gallery.add(f"Person {seed}-{index}", vector(seed * 100 + index), consent=True)


def _same_name_writer(path: str) -> None:
    gallery = Gallery(path, threshold=0.9)
    for _ in range(10):
        gallery.add("Herr X", vector(5), consent=True)


def test_concurrent_writers_do_not_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "gallery.db"
    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_writer, args=(str(path), seed)) for seed in (1, 2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=60)
        assert process.exitcode == 0

    gallery = Gallery(path)
    people = gallery.people()
    assert len(people) == 40
    assert sum(entry.samples for entry in people) == 40


def test_concurrent_enroll_of_same_name_creates_one_person(tmp_path: Path) -> None:
    """Ohne Sperre könnten zwei Prozesse zwei Personen mit gleichem Namen anlegen."""
    path = tmp_path / "same.db"
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_same_name_writer, args=(str(path),)) for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=60)
        assert process.exitcode == 0

    gallery = Gallery(path)
    people = gallery.people()
    assert len(people) == 1, f"mehrere Personen mit gleichem Namen: {people}"
    assert people[0].samples == 20
