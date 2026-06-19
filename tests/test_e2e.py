"""
End-to-end: the three seeded loads through push_delivery_record.

Asserts the full demo narrative:
  L1001 clean      -> invoiced, no discrepancies
  L2002 weight     -> flagged, NOT invoiced
  L3003 damage+exc -> flagged, NOT invoiced
"""

from __future__ import annotations

import requests

from tests.test_webhooks import first_result, vapi_envelope


def _push(client, args):
    return client.post("/webhook/push_delivery_record",
                       json=vapi_envelope("e2e", "push_delivery_record", args))


def _load(state, load_id):
    return next(l for l in state["loads"] if l["load_id"] == load_id)


def test_seeded_loads_drive_three_paths(client, faketms_server):
    # --- L1001: clean -> invoiced -------------------------------------- #
    _push(client, {
        "load_id": "L1001", "delivered_at": "2026-06-19T14:32:00",
        "recipient_name": "J. Rivera", "actual_pieces": 20, "actual_weight_lbs": 18000,
    })

    # --- L2002: weight variance -> flagged, held ----------------------- #
    # Expected 14000 lbs; report 12200 (~12.9% under) => warning.
    _push(client, {
        "load_id": "L2002", "delivered_at": "2026-06-19T09:40:00",
        "recipient_name": "M. Chen", "actual_pieces": 16, "actual_weight_lbs": 12200,
    })

    # --- L3003: damage + exception -> flagged, held -------------------- #
    _push(client, {
        "load_id": "L3003", "delivered_at": "2026-06-19T11:15:00",
        "recipient_name": "Yard Supervisor", "actual_pieces": 8, "actual_weight_lbs": 42000,
        "damage": True, "damage_notes": "two beams bent", "exception_type": "refused",
        "transcript_excerpt": "they wouldn't take the bent ones",
    })

    state = requests.get(f"{faketms_server}/state").json()

    # L1001 clean -> invoiced
    assert _load(state, "L1001")["status"] == "invoiced"
    assert not [d for d in state["discrepancies"] if d["load_id"] == "L1001"]

    # L2002 flagged + held at delivered (not invoiced)
    l2002 = _load(state, "L2002")
    assert l2002["status"] == "delivered"
    assert l2002["invoice_number"] is None
    d2002 = [d for d in state["discrepancies"] if d["load_id"] == "L2002"]
    assert {d["code"] for d in d2002} == {"weight_variance"}

    # L3003 flagged (damage + exception) + held
    l3003 = _load(state, "L3003")
    assert l3003["status"] == "delivered"
    assert l3003["invoice_number"] is None
    codes = {d["code"] for d in state["discrepancies"] if d["load_id"] == "L3003"}
    assert "damage" in codes and "exception" in codes
    # Severity stays specific per trigger.
    sev = {d["code"]: d["severity"]
           for d in state["discrepancies"] if d["load_id"] == "L3003"}
    assert sev["damage"] == "critical"


def test_every_pushed_load_has_a_pod_with_readback(client, faketms_server):
    for args in (
        {"load_id": "L1001", "delivered_at": "2026-06-19T14:32:00",
         "recipient_name": "J. Rivera", "actual_pieces": 20, "actual_weight_lbs": 18000},
        {"load_id": "L2002", "delivered_at": "2026-06-19T09:40:00",
         "recipient_name": "M. Chen", "actual_pieces": 16, "actual_weight_lbs": 12200},
    ):
        r = first_result(_push(client, args).get_json())
        assert r["result"]  # a spoken readback string came back

    state = requests.get(f"{faketms_server}/state").json()
    pods_by_load = {p["load_id"]: p for p in state["pods"]}
    assert pods_by_load["L1001"]["readback"]
    assert pods_by_load["L1001"]["clean"] is True
    assert pods_by_load["L2002"]["readback"]
    assert pods_by_load["L2002"]["clean"] is False
