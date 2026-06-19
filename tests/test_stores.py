"""
Storage-seam tests.

- Factory wiring (sqlite default, insforge on demand, unknown rejected).
- InsForgeStore exercised end-to-end against an in-memory PostgREST-lite fake,
  so the REST logic is proven without a live InsForge instance — and the exact
  request shaping (method/url/auth/filters) is asserted.
"""

from __future__ import annotations

import pytest
import requests

from faketms.stores import SqliteStore, get_store
from faketms.stores.insforge_store import InsForgeStore


# --- factory -------------------------------------------------------------- #
def test_factory_defaults_to_sqlite():
    assert isinstance(get_store(), SqliteStore)
    assert isinstance(get_store("sqlite"), SqliteStore)


def test_factory_returns_insforge_on_request():
    assert isinstance(get_store("insforge"), InsForgeStore)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        get_store("dynamodb")


# --- in-memory PostgREST-lite fake ---------------------------------------- #
class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeInsForge:
    """Implements just enough PostgREST semantics for the three faketms tables."""

    def __init__(self):
        self.tables = {"loads": [], "pods": [], "discrepancies": []}
        self._seq = {"pods": 0, "discrepancies": 0}
        self.calls = []

    def request(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append((method, url, dict(params or {}), json, dict(headers or {})))
        table = url.rsplit("/", 1)[-1]
        rows = self.tables[table]
        params = params or {}
        filters = {k: v for k, v in params.items() if k not in ("order", "limit")}

        def match(r):
            for col, expr in filters.items():
                if expr.startswith("eq."):
                    if str(r.get(col)) != expr[3:]:
                        return False
                elif expr == "not.is.null":
                    if r.get(col) is None:
                        return False
                else:
                    return False
            return True

        if method == "GET":
            out = [dict(r) for r in rows if match(r)]
            order = params.get("order")
            if order:
                col, _, direction = order.partition(".")
                out.sort(key=lambda r: r.get(col), reverse=(direction == "desc"))
            if params.get("limit"):
                out = out[: int(params["limit"])]
            return _Resp(200, out)
        if method == "POST":
            created = []
            for row in json:
                row = dict(row)
                if table in self._seq:
                    self._seq[table] += 1
                    row["id"] = self._seq[table]
                rows.append(row)
                created.append(row)
            return _Resp(201, created)
        if method == "PATCH":
            updated = []
            for r in rows:
                if match(r):
                    r.update(json)
                    updated.append(dict(r))
            return _Resp(200, updated)
        if method == "DELETE":
            self.tables[table] = [r for r in rows if not match(r)]
            return _Resp(204, [])
        return _Resp(405, {})


@pytest.fixture()
def insforge():
    fake = FakeInsForge()
    store = InsForgeStore(base_url="https://app.insforge.app", token="sekret", session=fake)
    return store, fake


# --- request shaping ------------------------------------------------------ #
def test_get_load_issues_correct_rest_call(insforge):
    store, fake = insforge
    store.init(reset=True)
    store.get_load("L1001")
    method, url, params, _body, headers = fake.calls[-1]
    assert method == "GET"
    assert url == "https://app.insforge.app/api/database/records/loads"
    assert params["load_id"] == "eq.L1001"
    assert headers["Authorization"] == "Bearer sekret"


# --- end-to-end behavior parity with sqlite ------------------------------- #
def test_init_seeds_three_pending_loads(insforge):
    store, _ = insforge
    store.init(reset=True)
    state = store.dump_state()
    assert {l["load_id"] for l in state["loads"]} == {"L1001", "L2002", "L3003"}
    assert all(l["status"] == "pending" for l in state["loads"])


def test_get_load_known_and_unknown(insforge):
    store, _ = insforge
    store.init(reset=True)
    assert store.get_load("L1001")["consignee"] == "Kroger DC #42"
    assert store.get_load("NOPE") is None


def test_pod_advances_to_delivered(insforge):
    store, _ = insforge
    store.init(reset=True)
    store.save_pod("L1001", {"load_id": "L1001", "delivered_at": "2026-06-19T14:00:00"},
                   "all good", True, "now")
    assert store.get_load("L1001")["status"] == "delivered"
    pod = next(p for p in store.dump_state()["pods"] if p["load_id"] == "L1001")
    assert pod["record"]["load_id"] == "L1001"  # record_json parsed back
    assert pod["clean"] is True


def test_invoice_then_pod_does_not_downgrade(insforge):
    store, _ = insforge
    store.init(reset=True)
    store.mark_invoiced("L1001", "INV-L1001-1")
    assert store.get_load("L1001")["status"] == "invoiced"
    # A late POD must not knock an invoiced load back to delivered.
    store.save_pod("L1001", {"load_id": "L1001"}, "late", True, "later")
    load = store.get_load("L1001")
    assert load["status"] == "invoiced"
    assert load["invoice_number"] == "INV-L1001-1"


def test_discrepancy_queued(insforge):
    store, _ = insforge
    store.init(reset=True)
    store.save_discrepancy("L2002", "weight_variance", "warning", "weight off",
                           "scale read low", "now")
    discs = store.dump_state()["discrepancies"]
    assert discs and discs[0]["code"] == "weight_variance"
    assert discs[0]["severity"] == "warning"
    assert discs[0]["transcript_excerpt"] == "scale read low"
