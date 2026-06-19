from __future__ import annotations

from typing import cast

import requests

from freightvoice.adapters.base import AdapterError, FactoringAdapter, LoadNotFoundError, TMSAdapter
from freightvoice.schemas import DeliveryRecord, Discrepancy, LoadContext


class FakeTMSAdapter(TMSAdapter):
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_load(self, load_id: str) -> LoadContext:
        payload = self._request("GET", f"/loads/{load_id}")
        return LoadContext(**payload)

    def write_pod(self, record: DeliveryRecord) -> None:
        self._request("POST", "/pod", json=record.model_dump(mode="json"))

    def trigger_invoice(self, load_id: str) -> str:
        payload = self._request("POST", f"/invoice/{load_id}")
        return str(payload["invoice_number"])

    def write_discrepancy(self, load_id: str, discrepancies: list[Discrepancy]) -> None:
        self._request(
            "POST",
            "/discrepancy",
            json={
                "load_id": load_id,
                "discrepancies_json": [item.model_dump(mode="json") for item in discrepancies],
            },
        )

    def schedule_callback(self, load_id: str, driver_phone: str | None, reason: str | None) -> None:
        self._request(
            "POST",
            "/callback",
            json={"load_id": load_id, "driver_phone": driver_phone, "reason": reason},
        )

    def get_state(self) -> dict[str, object]:
        return self._request("GET", "/state")

    def _request(self, method: str, path: str, json: dict[str, object] | None = None) -> dict[str, object]:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"FakeTMS unavailable: {exc}") from exc

        if response.status_code == 404:
            raise LoadNotFoundError(response.text)
        if response.status_code >= 400:
            raise AdapterError(f"FakeTMS returned {response.status_code}: {response.text}")
        return cast(dict[str, object], response.json())


class FakeFactoringAdapter(FactoringAdapter):
    def trigger_advance(self, load_id: str) -> str:
        return f"ADV-{load_id}"
