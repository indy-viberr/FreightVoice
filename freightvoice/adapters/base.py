"""
The adapter seam — the single boundary that makes this product real.

``freightvoice/`` contains NOTHING carrier-specific. It depends only on these
abstract interfaces. The demo wires in ``FakeTMSAdapter`` (talks to the faketms
service); production wires in ``SamsaraAdapter`` / ``MotiveAdapter`` / etc. by
implementing the same three methods. Switching is one env var + one class.

``LoadNotFound`` is raised by ``get_load`` so the webhook layer can turn it into
an agent-friendly "I couldn't find that load, can you re-read the number?"
rather than a 500.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import DeliveryRecord, LoadContext
from ..validation import Discrepancy


class LoadNotFound(Exception):
    """Raised by ``get_load`` when the TMS has no such load."""

    def __init__(self, load_id: str):
        self.load_id = load_id
        super().__init__(f"load not found: {load_id}")


class TMSAdapter(ABC):
    """Abstract carrier TMS. Implement these four methods to go live."""

    @abstractmethod
    def get_load(self, load_id: str) -> LoadContext:
        """Fetch pre-delivery load context. Raise ``LoadNotFound`` if absent."""

    @abstractmethod
    def write_pod(
        self,
        record: DeliveryRecord,
        readback: str | None,
        clean: bool,
    ) -> None:
        """Persist the proof-of-delivery and advance the load to 'delivered'."""

    @abstractmethod
    def trigger_invoice(self, load_id: str) -> str:
        """Kick off invoicing for a clean delivery. Return the invoice number."""

    @abstractmethod
    def write_discrepancy(self, load_id: str, discrepancy: Discrepancy,
                          transcript_excerpt: str | None) -> None:
        """Append a discrepancy to the carrier's exception queue.

        Part of the seam because the exception queue is carrier-owned: a real
        TMS routes these to its own AP/claims workflow.
        """


class FactoringAdapter(ABC):
    """Abstract factoring/quick-pay provider (RTS, Triumph, etc.)."""

    @abstractmethod
    def trigger_advance(self, load_id: str) -> str:
        """Request an advance against a clean, invoiced load. Return a ref id."""
