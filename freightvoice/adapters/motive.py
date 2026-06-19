"""
Motive (formerly KeepTruckin) TMS adapter — PRODUCTION STUB.

Proves the seam; not wired up. Going live = implement these four methods.

Motive API reference: https://developer.gomotive.com/reference
Auth: ``Authorization: Bearer <api_key>`` (or OAuth2). Base: https://api.gomotive.com
"""

from __future__ import annotations

import os

from ..schemas import DeliveryRecord, LoadContext
from ..validation import Discrepancy
from .base import TMSAdapter

MOTIVE_BASE = "https://api.gomotive.com"


class MotiveAdapter(TMSAdapter):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MOTIVE_API_KEY")

    def get_load(self, load_id: str) -> LoadContext:
        # GET {MOTIVE_BASE}/v1/dispatches/{id} -> map to LoadContext.
        raise NotImplementedError("wire to Motive sandbox: GET /v1/dispatches/{id}")

    def write_pod(self, record: DeliveryRecord, readback: str | None, clean: bool) -> None:
        # POST {MOTIVE_BASE}/v1/documents with the POD payload.
        raise NotImplementedError("wire to Motive sandbox: POST /v1/documents")

    def trigger_invoice(self, load_id: str) -> str:
        raise NotImplementedError("wire to carrier billing system")

    def write_discrepancy(self, load_id: str, discrepancy: Discrepancy,
                          transcript_excerpt: str | None) -> None:
        raise NotImplementedError("wire to carrier exception queue")
