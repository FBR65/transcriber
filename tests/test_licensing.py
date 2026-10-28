"""S31: Standardkonfiguration enthält keine nicht-kommerzielle Lizenz (SPEC D8 = a)."""

from __future__ import annotations

from transcriber.config import DEFAULT_ADAPTERS
from transcriber.licensing import blocked_defaults, defaults, for_adapter


def test_default_adapters_have_commercial_licences() -> None:
    blocked = blocked_defaults()
    assert blocked == (), f"nicht kommerziell nutzbar: {[entry.model for entry in blocked]}"
    for adapter in DEFAULT_ADAPTERS.values():
        entries = for_adapter(adapter)
        assert entries, f"kein Lizenzeintrag für Adapter {adapter!r}"
        for entry in entries:
            assert entry.commercial, entry.model
            assert "NC" not in entry.licence, entry.model


def test_licence_table_covers_every_default() -> None:
    covered = {entry.adapter for entry in defaults()}
    assert covered == set(DEFAULT_ADAPTERS.values())
