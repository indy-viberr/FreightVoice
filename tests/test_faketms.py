"""
Direct fake-TMS endpoint + state-transition tests.

Drives faketms straight (no middleware) to prove each carrier-facing endpoint
and the pending → delivered → invoiced lifecycle in isolation.
"""

from __future__ import annotations

import pytest

from faketms.app import create_app as create_faketms


@pytest.fixture()
def tms():
    app = create_faketms()  # reseeds the 3 demo loads
    app.testing = True
    return app.test_client()


def test_get_seeded_load_returns_context(tms):
    r = tms.get("/loads/L1001")
    assert r.status_code == 200
    data = r.get_json()
    assert data["consignee"] == "Kroger DC #42"
    assert data["status"] == "pending"


def test_get_unknown_load_404s(tms):
    r = tms.get("/loads/NOPE")
    assert r.status_code == 404
    assert r.get_json()["error"] == "load_not_found"


def test_three_loads_are_seeded(tms):
    state = tms.get("/state").get_json()
    assert {l["load_id"] for l in state["loads"]} == {"L1001", "L2002", "L3003"}
    assert all(l["status"] == "pending" for l in state["loads"])


def test_pod_marks_delivered(tms):
    tms.post("/pod", json={
        "load_id": "L1001",
        "record": {"load_id": "L1001", "delivered_at": "2026-06-19T14:00:00",
                   "actual_pieces": 20, "actual_weight_lbs": 18000},
        "readback": "all good", "clean": True,
    })
    state = tms.get("/state").get_json()
    load = next(l for l in state["loads"] if l["load_id"] == "L1001")
    assert load["status"] == "delivered"
    assert any(p["load_id"] == "L1001" for p in state["pods"])


def test_invoice_marks_invoiced_with_number(tms):
    tms.post("/pod", json={"load_id": "L1001", "record": {"load_id": "L1001"},
                           "readback": "x", "clean": True})
    r = tms.post("/invoice/L1001")
    assert r.status_code == 200
    inv = r.get_json()["invoice_number"]
    assert inv
    load = next(l for l in tms.get("/state").get_json()["loads"]
                if l["load_id"] == "L1001")
    assert load["status"] == "invoiced"
    assert load["invoice_number"] == inv


def test_clean_load_full_lifecycle(tms):
    """pending → delivered → invoiced."""
    assert next(l for l in tms.get("/state").get_json()["loads"]
                if l["load_id"] == "L1001")["status"] == "pending"
    tms.post("/pod", json={"load_id": "L1001", "record": {"load_id": "L1001"},
                           "readback": "x", "clean": True})
    assert next(l for l in tms.get("/state").get_json()["loads"]
                if l["load_id"] == "L1001")["status"] == "delivered"
    tms.post("/invoice/L1001")
    assert next(l for l in tms.get("/state").get_json()["loads"]
                if l["load_id"] == "L1001")["status"] == "invoiced"


def test_discrepancy_stored_in_queue(tms):
    tms.post("/discrepancy", json={
        "load_id": "L2002", "code": "weight_variance", "severity": "warning",
        "message": "weight off", "transcript_excerpt": "scale read low",
    })
    discs = tms.get("/state").get_json()["discrepancies"]
    assert any(d["load_id"] == "L2002" and d["severity"] == "warning" for d in discs)


def test_pod_then_no_invoice_stays_delivered(tms):
    """Discrepancy path: delivered but never invoiced."""
    tms.post("/pod", json={"load_id": "L2002", "record": {"load_id": "L2002"},
                           "readback": "held", "clean": False})
    tms.post("/discrepancy", json={"load_id": "L2002", "code": "weight_variance",
                                   "severity": "warning", "message": "off"})
    load = next(l for l in tms.get("/state").get_json()["loads"]
                if l["load_id"] == "L2002")
    assert load["status"] == "delivered"
    assert load["invoice_number"] is None
