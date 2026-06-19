from __future__ import annotations

import json
import os
import time

import requests


BASE_URL = os.getenv("FREIGHTVOICE_URL", "http://localhost:5000").rstrip("/")


def vapi_envelope(tool_call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
    }


def post_tool(endpoint: str, tool_call_id: str, name: str, arguments: dict[str, object]) -> str:
    response = requests.post(
        f"{BASE_URL}{endpoint}",
        json=vapi_envelope(tool_call_id, name, arguments),
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["results"][0]["result"])


def print_header(title: str) -> None:
    line = "=" * 58
    print(f"\n{line}\n {title}\n{line}")


def print_call(endpoint: str, payload: dict[str, object]) -> None:
    print(f"[->] {endpoint} {json.dumps(payload, indent=2)}")


def current_status(load_id: str) -> tuple[str, int]:
    response = requests.get(f"{BASE_URL}/state", timeout=10)
    response.raise_for_status()
    state = response.json()
    load = next(item for item in state["loads"] if item["load_id"] == load_id)
    discrepancy_count = len([item for item in state["discrepancies"] if item["load_id"] == load_id])
    return str(load["status"]), discrepancy_count


def main() -> None:
    scenarios: list[dict[str, object]] = [
        {
            "title": "SCENARIO 1: Clean Run - FV-DEMO-001",
            "load_id": "FV-DEMO-001",
            "push": {
                "load_id": "FV-DEMO-001",
                "delivered_at": "2026-06-19T20:14:00Z",
                "recipient_name": "Jane Smith",
                "actual_pieces": 24,
                "actual_weight_lbs": 18400,
                "damage": False,
                "accessorials": [],
            },
        },
        {
            "title": "SCENARIO 2: Weight Variance - FV-DEMO-002",
            "load_id": "FV-DEMO-002",
            "push": {
                "load_id": "FV-DEMO-002",
                "delivered_at": "2026-06-19T20:30:00Z",
                "recipient_name": "Sam Carter",
                "actual_pieces": 12,
                "actual_weight_lbs": 11500,
                "damage": False,
                "accessorials": [],
                "transcript_excerpt": "Driver confirmed 11,500 pounds on the scale ticket.",
            },
        },
        {
            "title": "SCENARIO 3: Damage + Detention - FV-DEMO-003",
            "load_id": "FV-DEMO-003",
            "push": {
                "load_id": "FV-DEMO-003",
                "delivered_at": "2026-06-19T21:45:00Z",
                "recipient_name": "Bob Martinez",
                "actual_pieces": 36,
                "actual_weight_lbs": 27000,
                "damage": True,
                "damage_notes": "3 pallets on NE corner of trailer showed forklift puncture. Photos submitted via SMS.",
                "accessorials": [
                    {"type": "detention", "duration_minutes": 135, "notes": "Arrived 14:00, unloading started 16:15"}
                ],
                "exception_type": "damage",
            },
        },
    ]

    for index, scenario in enumerate(scenarios, start=1):
        load_id = str(scenario["load_id"])
        print_header(str(scenario["title"]))

        get_args = {"load_id": load_id}
        print_call("get_load_context", get_args)
        spoken = post_tool("/webhook/get_load_context", f"tc_demo_{index:03d}_get", "get_load_context", get_args)
        print(f'[AGENT] "{spoken}"')

        time.sleep(2)

        push_args = scenario["push"]
        if not isinstance(push_args, dict):
            raise TypeError("scenario push payload must be a dict")
        print_call("push_delivery_record", push_args)
        spoken = post_tool("/webhook/push_delivery_record", f"tc_demo_{index:03d}_push", "push_delivery_record", push_args)
        print(f'[AGENT] "{spoken}"')

        status, discrepancy_count = current_status(load_id)
        if status == "invoiced":
            print("[OK] Invoice triggered. Clean record.")
        elif discrepancy_count:
            print(f"[OK] Dispatcher review queued. Discrepancies: {discrepancy_count}.")
        else:
            print(f"[OK] Load status: {status}.")

        time.sleep(2)


if __name__ == "__main__":
    main()

