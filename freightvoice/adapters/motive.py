from __future__ import annotations

from freightvoice.adapters.base import TMSAdapter
from freightvoice.schemas import DeliveryRecord, Discrepancy, LoadContext


class MotiveAdapter(TMSAdapter):
    """Production adapter seam for Motive/KeepTruckin."""

    def get_load(self, load_id: str) -> LoadContext:
        raise NotImplementedError("Wire to Motive route/load endpoint")

    def write_pod(self, record: DeliveryRecord) -> None:
        raise NotImplementedError("Wire to Motive document upload endpoint")

    def trigger_invoice(self, load_id: str) -> str:
        raise NotImplementedError("Wire to Motive completion/invoice workflow")

    def write_discrepancy(self, load_id: str, discrepancies: list[Discrepancy]) -> None:
        raise NotImplementedError("Wire to Motive notes or dispatcher alert workflow")

