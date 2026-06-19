from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tests.conftest import vapi_envelope


def post_tool(client: Any, path: str, tool_id: str, name: str, args: dict[str, Any]) -> str:
    response = client.post(path, json=vapi_envelope(tool_id, name, args))
    assert response.status_code == 200
    return response.get_json()["results"][0]["result"]


def test_e2e_clean_load(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    post_tool(client, "/webhook/get_load_context", "tc_e2e_001_get", "get_load_context", {"load_id": "FV-DEMO-001"})
    post_tool(
        client,
        "/webhook/push_delivery_record",
        "tc_e2e_001_push",
        "push_delivery_record",
        {
            "load_id": "FV-DEMO-001",
            "delivered_at": "2026-06-19T20:14:00Z",
            "recipient_name": "Jane Smith",
            "actual_pieces": 24,
            "actual_weight_lbs": 18400,
            "damage": False,
            "accessorials": [],
        },
    )
    state = fake_tms_state()
    load = next(item for item in state["loads"] if item["load_id"] == "FV-DEMO-001")
    assert load["status"] == "invoiced"
    assert len(state["pods"]) == 1
    assert state["discrepancies"] == []


def test_e2e_weight_variance(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    post_tool(client, "/webhook/get_load_context", "tc_e2e_002_get", "get_load_context", {"load_id": "FV-DEMO-002"})
    post_tool(
        client,
        "/webhook/push_delivery_record",
        "tc_e2e_002_push",
        "push_delivery_record",
        {
            "load_id": "FV-DEMO-002",
            "delivered_at": "2026-06-19T20:30:00Z",
            "recipient_name": "Sam Carter",
            "actual_pieces": 12,
            "actual_weight_lbs": 11500,
            "damage": False,
            "accessorials": [],
            "transcript_excerpt": "Driver confirmed 11,500 pounds on the scale ticket.",
        },
    )
    state = fake_tms_state()
    load = next(item for item in state["loads"] if item["load_id"] == "FV-DEMO-002")
    assert load["status"] == "delivered"
    assert state["invoices"] == []
    assert state["discrepancies"][0]["trigger"] == "weight_variance"
    assert state["discrepancies"][0]["severity"] == "critical"


def test_e2e_damage_with_accessorial(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    post_tool(client, "/webhook/get_load_context", "tc_e2e_003_get", "get_load_context", {"load_id": "FV-DEMO-003"})
    post_tool(
        client,
        "/webhook/push_delivery_record",
        "tc_e2e_003_push",
        "push_delivery_record",
        {
            "load_id": "FV-DEMO-003",
            "delivered_at": "2026-06-19T21:45:00Z",
            "recipient_name": "Bob Martinez",
            "actual_pieces": 36,
            "actual_weight_lbs": 27000,
            "damage": True,
            "damage_notes": "3 pallets on NE corner of trailer showed forklift puncture.",
            "accessorials": [
                {"type": "detention", "duration_minutes": 135, "notes": "Arrived 14:00, unloading started 16:15"}
            ],
            "exception_type": "damage",
        },
    )
    state = fake_tms_state()
    assert state["invoices"] == []
    assert state["discrepancies"][0]["trigger"] == "damage_reported"
    assert state["discrepancies"][0]["severity"] == "critical"
    assert state["pods"][0]["accessorials"][0]["type"] == "detention"
    assert state["pods"][0]["accessorials"][0]["duration_minutes"] == 135

