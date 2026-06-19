from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tests.conftest import vapi_envelope


def clean_record(load_id: str = "FV-DEMO-001") -> dict[str, Any]:
    return {
        "load_id": load_id,
        "delivered_at": "2026-06-19T20:14:00Z",
        "recipient_name": "Jane Smith",
        "actual_pieces": 24,
        "actual_weight_lbs": 18400,
        "damage": False,
        "accessorials": [],
    }


def result_text(response_json: dict[str, Any]) -> str:
    return response_json["results"][0]["result"]


def test_get_load_context_found(client: Any) -> None:
    response = client.post(
        "/webhook/get_load_context",
        json=vapi_envelope("tc_get_1", "get_load_context", {"load_id": "FV-DEMO-001"}),
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["results"][0]["toolCallId"] == "tc_get_1"
    assert "XYZ Distribution Atlanta" in result_text(payload)


def test_get_load_context_not_found(client: Any) -> None:
    response = client.post(
        "/webhook/get_load_context",
        json=vapi_envelope("tc_get_missing", "get_load_context", {"load_id": "NOPE"}),
    )
    assert response.status_code == 200
    assert "couldn't find load" in result_text(response.get_json())


def test_push_delivery_record_clean(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    response = client.post(
        "/webhook/push_delivery_record",
        json=vapi_envelope("tc_push_clean", "push_delivery_record", clean_record()),
    )
    assert response.status_code == 200
    assert "Invoice submitted" in result_text(response.get_json())
    state = fake_tms_state()
    load = next(item for item in state["loads"] if item["load_id"] == "FV-DEMO-001")
    assert load["status"] == "invoiced"


def test_push_delivery_record_discrepancy(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    record = clean_record("FV-DEMO-002") | {
        "actual_pieces": 12,
        "actual_weight_lbs": 11500,
    }
    response = client.post(
        "/webhook/push_delivery_record",
        json=vapi_envelope("tc_push_discrepancy", "push_delivery_record", record),
    )
    assert response.status_code == 200
    assert "flagged for your dispatcher" in result_text(response.get_json())
    state = fake_tms_state()
    assert len(state["discrepancies"]) == 1
    assert state["discrepancies"][0]["trigger"] == "weight_variance"


def test_flag_discrepancy_explicit(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    response = client.post(
        "/webhook/flag_discrepancy",
        json=vapi_envelope(
            "tc_flag",
            "flag_discrepancy",
            {
                "load_id": "FV-DEMO-001",
                "description": "Driver reports receiver closed early.",
                "transcript_excerpt": "Receiver closed the gate.",
            },
        ),
    )
    assert response.status_code == 200
    assert "Flagged" in result_text(response.get_json())
    state = fake_tms_state()
    assert state["discrepancies"][0]["trigger"] == "manual_flag"


def test_schedule_callback(client: Any, fake_tms_state: Callable[[], dict[str, Any]]) -> None:
    response = client.post(
        "/webhook/schedule_callback",
        json=vapi_envelope(
            "tc_callback",
            "schedule_callback",
            {"load_id": "FV-DEMO-001", "driver_phone": "+15551234567", "reason": "Driver has to roll."},
        ),
    )
    assert response.status_code == 200
    assert "Someone will call you back" in result_text(response.get_json())
    state = fake_tms_state()
    assert len(state["callbacks"]) == 1


def test_malformed_envelope(client: Any) -> None:
    response = client.post("/webhook/get_load_context", json={"not_message": {}})
    assert response.status_code == 400


def test_dashboard_visible(client: Any) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "FreightVoice" in response.get_data(as_text=True)
