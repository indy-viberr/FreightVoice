from __future__ import annotations

from abc import ABC, abstractmethod

from freightvoice.schemas import DeliveryRecord, Discrepancy, LoadContext


class TMSAdapter(ABC):
    """Abstract interface for all TMS integrations."""

    @abstractmethod
    def get_load(self, load_id: str) -> LoadContext:
        """Fetch load context by load_id or pro_number."""

    @abstractmethod
    def write_pod(self, record: DeliveryRecord) -> None:
        """Persist the delivery record as a POD in the TMS."""

    @abstractmethod
    def trigger_invoice(self, load_id: str) -> str:
        """Mark load as invoiced and return an invoice reference."""

    @abstractmethod
    def write_discrepancy(self, load_id: str, discrepancies: list[Discrepancy]) -> None:
        """Append discrepancy records to the dispatcher review queue."""


class FactoringAdapter(ABC):
    @abstractmethod
    def trigger_advance(self, load_id: str) -> str:
        """Notify the factoring company that a clean POD has been received."""


class LoadNotFoundError(Exception):
    pass


class AdapterError(Exception):
    pass

