"""Adapter factory — picks the concrete TMS/factoring adapter from env config.

This is the whole switch-to-production surface: ``FREIGHTVOICE_TMS=samsara`` and
the rest of the app is unchanged.
"""

from __future__ import annotations

from .. import config
from .base import FactoringAdapter, LoadNotFound, TMSAdapter
from .fake import FakeFactoringAdapter, FakeTMSAdapter

__all__ = [
    "TMSAdapter",
    "FactoringAdapter",
    "LoadNotFound",
    "FakeTMSAdapter",
    "FakeFactoringAdapter",
    "get_tms_adapter",
    "get_factoring_adapter",
]


def get_tms_adapter(backend: str | None = None) -> TMSAdapter:
    backend = (backend or config.TMS_BACKEND).lower()
    if backend == "fake":
        return FakeTMSAdapter()
    if backend == "samsara":
        from .samsara import SamsaraAdapter

        return SamsaraAdapter()
    if backend == "motive":
        from .motive import MotiveAdapter

        return MotiveAdapter()
    raise ValueError(f"unknown FREIGHTVOICE_TMS backend: {backend!r}")


def get_factoring_adapter() -> FactoringAdapter:
    if not config.FACTORING_ENABLED:
        return _NullFactoringAdapter()
    # Only the fake is runnable without credentials; RTS is a documented stub.
    return FakeFactoringAdapter()


class _NullFactoringAdapter(FactoringAdapter):
    """Used when factoring is disabled — advance is a no-op."""

    def trigger_advance(self, load_id: str) -> str:  # pragma: no cover - trivial
        return ""
