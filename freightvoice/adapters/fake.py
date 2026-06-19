"""
Working adapters that talk to the faketms service over HTTP.

This is real code on the real path — the only thing "fake" is what's on the
other end of the socket. Swapping in ``SamsaraAdapter`` changes these HTTP calls
to Samsara's REST API and nothing else in ``freightvoice/`` moves.
"""

from __future__ import annotations

import requests

from .. import config
from ..schemas import DeliveryRecord, LoadContext
from ..validation import Discrepancy
from .base import FactoringAdapter, LoadNotFound, TMSAdapter


class FakeTMSAdapter(TMSAdapter):
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or config.FAKETMS_URL).rstrip("/")
        self.timeout = timeout or config.HTTP_TIMEOUT

    def get_load(self, load_id: str) -> LoadContext:
        resp = requests.get(f"{self.base_url}/loads/{load_id}", timeout=self.timeout)
        if resp.status_code == 404:
            raise LoadNotFound(load_id)
        resp.raise_for_status()
        data = resp.json()
        # The TMS row carries lifecycle columns the agent doesn't need; pluck
        # exactly the LoadContext fields so schema validation stays strict.
        return LoadContext(
            load_id=data["load_id"],
            shipper=data["shipper"],
            consignee=data["consignee"],
            commodity=data["commodity"],
            expected_pieces=data["expected_pieces"],
            expected_weight_lbs=data["expected_weight_lbs"],
            scheduled_delivery=data["scheduled_delivery"],
            equipment_type=data["equipment_type"],
        )

    def write_pod(self, record: DeliveryRecord, readback: str | None, clean: bool) -> None:
        resp = requests.post(
            f"{self.base_url}/pod",
            json={
                "load_id": record.load_id,
                "record": record.model_dump(mode="json"),
                "readback": readback,
                "clean": clean,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def trigger_invoice(self, load_id: str) -> str:
        resp = requests.post(f"{self.base_url}/invoice/{load_id}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["invoice_number"]

    def write_discrepancy(self, load_id: str, discrepancy: Discrepancy,
                          transcript_excerpt: str | None) -> None:
        resp = requests.post(
            f"{self.base_url}/discrepancy",
            json={
                "load_id": load_id,
                "code": discrepancy.code.value,
                "severity": discrepancy.severity.value,
                "message": discrepancy.message,
                "transcript_excerpt": transcript_excerpt,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()


class FakeFactoringAdapter(FactoringAdapter):
    """Stand-in for a quick-pay provider. Returns a believable advance ref.

    No money moves; this exists so the clean-path demo can show the
    "delivered -> invoiced -> advance requested" cascade end to end.
    """

    def trigger_advance(self, load_id: str) -> str:
        return f"ADV-{load_id}"
