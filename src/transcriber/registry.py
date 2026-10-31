"""Registry für Adapter. Plug-ins melden sich über entry points an (SPEC D5 = a)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import entry_points
from typing import Any

from .errors import UnknownAdapterError

Factory = Callable[[], Any]
Register = Callable[["Registry"], None]

ENTRY_POINT_GROUP = "transcriber.adapters"


class Registry:
    """Namen → Fabrik, getrennt je Port."""

    def __init__(self) -> None:
        self._factories: dict[str, dict[str, Factory]] = {}
        self._discovered = False

    def register(self, port: str, name: str, factory: Factory) -> None:
        if not name:
            raise ValueError("adapter name must not be empty")
        self._factories.setdefault(port, {})[name] = factory

    def names(self, port: str) -> list[str]:
        return sorted(self._factories.get(port, {}))

    def ports(self) -> list[str]:
        return sorted(self._factories)

    def has(self, port: str, name: str) -> bool:
        return name in self._factories.get(port, {})

    def create(self, port: str, name: str, **options: Any) -> Any:
        self.discover()
        try:
            factory = self._factories[port][name]
        except KeyError:
            raise UnknownAdapterError(port, name, self.names(port)) from None
        if options:
            return factory(**options)
        return factory()

    def discover(self, plugins: Iterable[Any] | None = None) -> None:
        """Lädt entry points der Gruppe `transcriber.adapters`.

        Jeder Einstiegspunkt liefert eine Funktion, die die Registry füllt.
        """
        if self._discovered and plugins is None:
            return
        sources = entry_points(group=ENTRY_POINT_GROUP) if plugins is None else plugins
        for entry_point in sources:
            register = entry_point.load()
            if not callable(register):
                raise TypeError(f"entry point {entry_point.name!r} is not callable")
            register(self)
        self._discovered = True


DEFAULT_REGISTRY = Registry()
