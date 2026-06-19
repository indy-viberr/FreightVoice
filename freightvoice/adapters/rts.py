"""
RTS Financial factoring adapter — PRODUCTION STUB.

Proves the FactoringAdapter seam. On a clean, invoiced load, production would
request a same-day advance against the receivable here.

RTS Pro API: partner-issued credentials; endpoints provided at integration time.
Auth: API key / partner token in the ``Authorization`` header.
"""

from __future__ import annotations

import os

from .base import FactoringAdapter


class RTSFactoringAdapter(FactoringAdapter):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("RTS_API_KEY")

    def trigger_advance(self, load_id: str) -> str:
        # POST to RTS Pro funding endpoint with the invoice reference.
        raise NotImplementedError("wire to RTS Pro funding API")
