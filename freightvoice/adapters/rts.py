from __future__ import annotations

from freightvoice.adapters.base import FactoringAdapter


class RTSAdapter(FactoringAdapter):
    """Production adapter seam for RTS factoring advances."""

    def trigger_advance(self, load_id: str) -> str:
        raise NotImplementedError("Wire to RTS factoring advance API")

