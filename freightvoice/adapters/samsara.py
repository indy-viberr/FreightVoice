from __future__ import annotations

from freightvoice.adapters.base import TMSAdapter
from freightvoice.schemas import DeliveryRecord, Discrepancy, LoadContext


class SamsaraAdapter(TMSAdapter):
    """
    Production adapter for Samsara Fleet Management.

    Auth: Bearer token in Authorization header.
    Base URL: https://api.samsara.com
    Docs: https://developers.samsara.com/reference/getallroutes

    Relevant endpoints:
      GET  /fleet/routes/{id}    -> get_load
      POST /fleet/document-types -> write_pod
      POST /fleet/trips/{id}/end -> trigger_invoice
    """

    def get_load(self, load_id: str) -> LoadContext:
        raise NotImplementedError("Wire to Samsara sandbox: GET /fleet/routes/{id}")

    def write_pod(self, record: DeliveryRecord) -> None:
        raise NotImplementedError("Wire to Samsara sandbox: POST /fleet/document-types")

    def trigger_invoice(self, load_id: str) -> str:
        raise NotImplementedError("Wire to Samsara sandbox: POST /fleet/trips/{id}/end")

    def write_discrepancy(self, load_id: str, discrepancies: list[Discrepancy]) -> None:
        raise NotImplementedError("Wire to Samsara: POST custom webhook or fleet document")

