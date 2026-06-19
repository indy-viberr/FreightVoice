"""
Webhook contract tests.

Post Vapi-shaped tool calls to each endpoint and assert (a) the response matches
the Vapi ``results[]`` envelope keyed by toolCallId and (b) the fake TMS state
actually changed.
"""

from __future__ import annotations

import json

import requests


def vapi_envelope(tool_call_id: str, name: str, arguments: dict) -> dict:
    """Build a Vapi server-tool request body."""
    return {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {"id": tool_call_id, "type": "function",
                 "function": {"name": name, "arguments": arguments}},
            ],
        }
    }


def first_result(resp_json: dict) -> dict:
    assert "results" in resp_json, resp_json
    assert len(resp_json["results"]) == 1
    return resp_json["results"][0]


# --- get_load_context ----------------------------------------------------- #
def test_get_load_context_returns_load(client):
    resp = client.post("/webhook/get_load_context",
                       json=vapi_envelope("call_1", "get_load_context", {"load_id": "L1001"}))
    assert resp.status_code == 200
    r = first_result(resp.get_json())
    assert r["toolCallId"] == "call_1"
    payload = json.loads(r["result"])
    assert payload["found"] is True
    assert payload["load"]["consignee"] == "Kroger DC #42"


def test_get_load_context_unknown_load_tells_agent(client):
    resp = client.post("/webhook/get_load_context",
                       json=vapi_envelope("call_2", "get_load_context", {"load_id": "NOPE"}))
    r = first_result(resp.get_json())
    payload = json.loads(r["result"])
    assert payload["found"] is False
    assert "re-read" in payload["message"].lower()


def test_get_load_context_accepts_pro_number_alias(client):
    resp = client.post("/webhook/get_load_context",
                       json=vapi_envelope("c", "get_load_context", {"pro_number": "L2002"}))
    payload = json.loads(first_result(resp.get_json())["result"])
    assert payload["found"] is True
    assert payload["load"]["load_id"] == "L2002"


# --- push_delivery_record ------------------------------------------------- #
def _clean_record_args() -> dict:
    return {
        "load_id": "L1001",
        "delivered_at": "2026-06-19T14:32:00",
        "recipient_name": "J. Rivera",
        "actual_pieces": 20,
        "actual_weight_lbs": 18000,
    }


def test_push_clean_record_invoices_and_changes_tms_state(client, faketms_server):
    resp = client.post("/webhook/push_delivery_record",
                       json=vapi_envelope("p1", "push_delivery_record", _clean_record_args()))
    assert resp.status_code == 200
    r = first_result(resp.get_json())
    assert r["toolCallId"] == "p1"
    assert "billing" in r["result"].lower()

    # TMS state changed: load is invoiced, a POD exists.
    state = requests.get(f"{faketms_server}/state").json()
    load = next(l for l in state["loads"] if l["load_id"] == "L1001")
    assert load["status"] == "invoiced"
    assert load["invoice_number"]
    assert any(p["load_id"] == "L1001" for p in state["pods"])


def test_push_validation_error_is_agent_friendly(client):
    bad = _clean_record_args() | {"actual_pieces": -5}
    resp = client.post("/webhook/push_delivery_record",
                       json=vapi_envelope("p2", "push_delivery_record", bad))
    r = first_result(resp.get_json())
    # No raw 500 / stack trace leaks to the agent.
    assert resp.status_code == 200
    assert "again" in r["result"].lower()


# --- flag_discrepancy ----------------------------------------------------- #
def test_flag_discrepancy_writes_to_queue(client, faketms_server):
    args = {"load_id": "L3003", "reason": "Driver says seal was broken on arrival",
            "severity": "critical", "transcript_excerpt": "the seal was already cut"}
    resp = client.post("/webhook/flag_discrepancy",
                       json=vapi_envelope("f1", "flag_discrepancy", args))
    r = first_result(resp.get_json())
    assert "flagged" in r["result"].lower()

    state = requests.get(f"{faketms_server}/state").json()
    flagged = [d for d in state["discrepancies"] if d["load_id"] == "L3003"]
    assert flagged
    assert flagged[0]["severity"] == "critical"
    assert flagged[0]["transcript_excerpt"] == "the seal was already cut"


# --- schedule_callback ---------------------------------------------------- #
def test_schedule_callback_records_intent(client):
    args = {"load_id": "L2002", "reason": "call dropped", "phone": "+15125550100"}
    resp = client.post("/webhook/schedule_callback",
                       json=vapi_envelope("s1", "schedule_callback", args))
    r = first_result(resp.get_json())
    assert "callback" in r["result"].lower()

    # Surfaced on the dashboard state.
    state = client.get("/api/state").get_json()
    assert any(c["load_id"] == "L2002" for c in state["callbacks"])


# --- envelope robustness -------------------------------------------------- #
def test_handles_arguments_as_json_string(client):
    """Vapi sometimes sends function.arguments as a JSON-encoded string."""
    body = {"message": {"type": "tool-calls", "toolCalls": [
        {"id": "j1", "type": "function",
         "function": {"name": "get_load_context",
                      "arguments": json.dumps({"load_id": "L1001"})}}]}}
    resp = client.post("/webhook/get_load_context", json=body)
    payload = json.loads(first_result(resp.get_json())["result"])
    assert payload["found"] is True
