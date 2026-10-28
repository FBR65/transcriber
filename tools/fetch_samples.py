#!/usr/bin/env python3
"""Lädt Testton. Die Dateien gehören nicht ins Repo.

jfk.wav: Ausschnitt einer Rede von John F. Kennedy (1961). Werk der US-Regierung,
gemeinfrei. Quelle: whisper.cpp-Beispielsammlung.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache" / "transcriber" / "samples"
SOURCES = {
    "jfk.wav": "https://github.com/ggml-org/whisper.cpp/raw/master/samples/jfk.wav",
}


def fetch(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if target.is_file() and target.stat().st_size > 1000:
        return target
    url = SOURCES[name]
    print(f"lade {url}")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        target.write_bytes(response.read())
    print(f"{target} ({target.stat().st_size} Bytes)")
    return target


def main(argv: list[str]) -> int:
    names = argv[1:] or list(SOURCES)
    for name in names:
        if name not in SOURCES:
            print(f"unbekannt: {name}", file=sys.stderr)
            return 2
        fetch(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
