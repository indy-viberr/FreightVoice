"""
Samsara TMS adapter — PRODUCTION STUB.

This is not wired up. It exists to prove the seam is real: every method names the
actual Samsara REST endpoint and auth it would call, so "going to production" is
implementing this one class and flipping FREIGHTVOICE_TMS=samsara.

Samsara API reference: https://developers.samsara.com/reference
Auth: Bearer token in the ``Authorization`` header (API token from the Samsara
dashboard, scoped to the org). Base URL: https://api.samsara.com
"""

from __future__ import annotations

import os

from ..schemas import DeliveryRecord, LoadContext
from ..validation import Discrepancy
from .base import FactoringAdapter, TMSAdapter

SAMSARA_BASE = "https://api.samsara.com"


class SamsaraAdapter(TMSAdapter):
    def __init__(self, api_token: str | None = None):
        # Real impl: token = api_token or os.environ["SAMSARA_API_TOKEN"]
        self.api_token = api_token or os.environ.get("SAMSARA_API_TOKEN")

    def get_load(self, load_id: str) -> LoadContext:
        # GET {SAMSARA_BASE}/fleet/routes/{routeId}  (or /v1/fleet/dispatch/routes)
        # Map the route stop -> LoadContext. Raise LoadNotFound on 404.
        # Header: Authorization: Bearer <api_token>
        raise NotImplementedError("wire to Samsara sandbox: GET /fleet/routes/{id}")

    def write_pod(self, record: DeliveryRecord, readback: str | None, clean: bool) -> None:
        # POST {SAMSARA_BASE}/fleet/documents  with the POD payload + signature.
        raise NotImplementedError("wire to Samsara sandbox: POST /fleet/documents")

    def trigger_invoice(self, load_id: str) -> str:
        # Samsara itself doesn't invoice; in production this calls the carrier's
        # billing system (e.g. McLeod / TruckMate) keyed off the completed route.
        raise NotImplementedError("wire to carrier billing system")

    def write_discrepancy(self, load_id: str, discrepancy: Discrepancy,
                          transcript_excerpt: str | None) -> None:
        # POST to the carrier's exception/claims queue.
        raise NotImplementedError("wire to carrier exception queue")
