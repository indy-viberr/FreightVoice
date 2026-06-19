"""Storage-backend factory for the fake TMS.

``FAKETMS_STORAGE=sqlite`` (default) | ``insforge``. This is the whole switch:
the service layer in ``faketms/app.py`` only ever sees the ``Store`` interface.
"""

from __future__ import annotations

import os

from .base import Store
from .sqlite_store import SqliteStore

__all__ = ["Store", "SqliteStore", "get_store"]


def get_store(backend: str | None = None) -> Store:
    backend = (backend or os.environ.get("FAKETMS_STORAGE", "sqlite")).lower()
    if backend == "sqlite":
        return SqliteStore()
    if backend == "insforge":
        # Imported lazily so the demo never needs InsForge config to boot.
        from .insforge_store import InsForgeStore

        return InsForgeStore()
    raise ValueError(f"unknown FAKETMS_STORAGE backend: {backend!r}")
