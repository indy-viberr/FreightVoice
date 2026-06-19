"""
Storage seam for the fake TMS.

Same idea as the ``TMSAdapter`` seam on the FreightVoice side: the faketms
service depends only on this ``Store`` interface, and a concrete backend is
chosen by env var. Two ship:

* ``SqliteStore``   — stdlib sqlite3, zero-config. The demo default.
* ``InsForgeStore`` — InsForge (managed Postgres + auto REST API) as the
                      system-of-record. Switch with ``FAKETMS_STORAGE=insforge``.

The methods mirror exactly what ``faketms/app.py`` needs, so swapping backends
changes nothing in the service layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Store(ABC):
    @abstractmethod
    def init(self, reset: bool = True) -> None:
        """Create/ensure tables and (re)seed the demo loads."""

    @abstractmethod
    def get_load(self, load_id: str) -> dict[str, Any] | None:
        """Return the load row, or None if unknown."""

    @abstractmethod
    def save_pod(self, load_id: str, record_json: dict[str, Any],
                 readback: str | None, clean: bool, now: str) -> None:
        """Persist a POD and advance the load to 'delivered' (never downgrade)."""

    @abstractmethod
    def mark_invoiced(self, load_id: str, invoice_number: str) -> None:
        """Mark a load invoiced with the given invoice number."""

    @abstractmethod
    def save_discrepancy(self, load_id: str, code: str, severity: str,
                         message: str, transcript_excerpt: str | None,
                         now: str) -> None:
        """Append a discrepancy to the queue."""

    @abstractmethod
    def dump_state(self) -> dict[str, Any]:
        """Return {loads, pods, discrepancies} for the dashboard and tests."""
