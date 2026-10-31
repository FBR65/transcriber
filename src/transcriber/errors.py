"""Fehlerklassen. Jeder Fehler trägt einen i18n-Schlüssel und seine Parameter."""

from __future__ import annotations

from collections.abc import Sequence


class TranscriberError(Exception):
    """Basisklasse. `key` ist der i18n-Schlüssel, `params` füllt ihn."""

    key = "error.generic"
    exit_code = 1

    def params(self) -> dict[str, object]:
        return {}

    def localized(self, lang: str = "de") -> str:
        from .i18n import translate

        return translate(self.key, lang, **self.params())


class UnknownAdapterError(TranscriberError):
    key = "error.unknown_adapter"

    def __init__(self, port: str, name: str, available: Sequence[str]) -> None:
        self.port = port
        self.name = name
        self.available = sorted(available)
        super().__init__(f"unknown adapter {name!r} for port {port!r}")

    def params(self) -> dict[str, object]:
        return {
            "port": self.port,
            "name": self.name,
            "available": ", ".join(self.available) or "-",
        }


class UnsupportedLanguageError(TranscriberError):
    key = "error.unsupported_language"
    exit_code = 2

    def __init__(self, language: str, available: Sequence[str]) -> None:
        self.language = language
        self.available = sorted(available)
        super().__init__(f"unsupported target language {language!r}")

    def params(self) -> dict[str, object]:
        return {"language": self.language, "available": ", ".join(self.available) or "-"}


class AudioDecodeError(TranscriberError):
    key = "error.audio_decode"

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"cannot decode audio {path!r}: {detail}")

    def params(self) -> dict[str, object]:
        return {"path": self.path, "detail": self.detail or "-"}


class GalleryConsentError(TranscriberError):
    """Ohne Zustimmung wird kein Stimmabdruck gespeichert (SPEC 7, S19)."""

    key = "error.gallery_consent"
    exit_code = 2

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"no consent for voiceprint of {name!r}")

    def params(self) -> dict[str, object]:
        return {"name": self.name}


class PersonNotFoundError(TranscriberError):
    key = "error.person_not_found"
    exit_code = 2

    def __init__(self, reference: str) -> None:
        self.reference = reference
        super().__init__(f"no person for {reference!r}")

    def params(self) -> dict[str, object]:
        return {"reference": self.reference}
