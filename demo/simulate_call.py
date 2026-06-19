#!/usr/bin/env python3
"""
Simulate the phone call without a phone.

Posts realistic Vapi server-tool payloads to the running FreightVoice service
for each of the three seeded loads, printing the agent's spoken readback at every
step. This is:

  * the fallback if live telephony flakes on stage, and
  * the thing you screen-record for the Twitter clip.

Run (both services must be up — `make demo` or `./run.sh`):
    python demo/simulate_call.py
    python demo/simulate_call.py --base-url http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import requests

# Each scenario maps to one seeded load and one discrepancy path.
SCENARIOS = [
    {
        "title": "Load L1001 — clean delivery",
        "load_id": "L1001",
        "record": {
            "load_id": "L1001",
            "delivered_at": "2026-06-19T14:32:00",
            "recipient_name": "J. Rivera",
            "actual_pieces": 20,
            "actual_weight_lbs": 18000,
            "accessorials": [{"type": "liftgate"}],
            "transcript_excerpt": "all twenty on the dock, Rivera signed",
        },
    },
    {
        "title": "Load L2002 — weight variance (held for review)",
        "load_id": "L2002",
        "record": {
            "load_id": "L2002",
            "delivered_at": "2026-06-19T09:40:00",
            "recipient_name": "M. Chen",
            "actual_pieces": 16,
            "actual_weight_lbs": 12200,
            "accessorials": [{"type": "detention", "duration_minutes": 95}],
            "transcript_excerpt": "scale read way under what the BOL said",
        },
    },
    {
        "title": "Load L3003 — damage + refused (held for review)",
        "load_id": "L3003",
        "record": {
            "load_id": "L3003",
            "delivered_at": "2026-06-19T11:15:00",
            "recipient_name": "Yard Supervisor",
            "actual_pieces": 8,
            "actual_weight_lbs": 42000,
            "damage": True,
            "damage_notes": "two beams bent in transit",
            "exception_type": "refused",
            "transcript_excerpt": "they wouldn't take the bent ones",
        },
    },
]


# --- pretty terminal output ---------------------------------------------- #
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"


def _vapi_body(tool_name: str, args: dict) -> dict:
    return {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": f"call_{tool_name}_{int(time.time()*1000) % 100000}",
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args},
                }
            ],
        }
    }


def _call(base_url: str, tool_name: str, args: dict) -> str:
    resp = requests.post(f"{base_url}/webhook/{tool_name}",
                         json=_vapi_body(tool_name, args), timeout=10)
    resp.raise_for_status()
    return resp.json()["results"][0]["result"]


def run(base_url: str) -> int:
    try:
        requests.get(f"{base_url}/health", timeout=3).raise_for_status()
    except requests.RequestException:
        print(f"{C.YELLOW}FreightVoice not reachable at {base_url}. "
              f"Start it first (make demo / ./run.sh).{C.RESET}")
        return 1

    print(f"\n{C.BOLD}FreightVoice — simulated post-delivery calls{C.RESET}")
    print(f"{C.DIM}Posting Vapi-shaped tool calls to {base_url}{C.RESET}\n")

    for sc in SCENARIOS:
        print(f"{C.BOLD}{C.BLUE}▶ {sc['title']}{C.RESET}")

        # 1. Agent pulls context to confirm-not-dictate.
        ctx_raw = _call(base_url, "get_load_context", {"load_id": sc["load_id"]})
        ctx = json.loads(ctx_raw)
        if ctx.get("found"):
            load = ctx["load"]
            print(f"  {C.CYAN}get_load_context{C.RESET}  "
                  f"{load['shipper']} → {load['consignee']}, "
                  f"{load['expected_pieces']} pcs / {load['expected_weight_lbs']:.0f} lbs "
                  f"({load['commodity']})")
        else:
            print(f"  {C.YELLOW}get_load_context{C.RESET}  {ctx.get('message')}")

        # 2. Agent pushes the completed delivery record.
        readback = _call(base_url, "push_delivery_record", sc["record"])
        clean = "billing" in readback.lower()
        tag = f"{C.GREEN}CLEAN → INVOICED{C.RESET}" if clean else f"{C.YELLOW}HELD FOR REVIEW{C.RESET}"
        print(f"  {C.CYAN}push_delivery_record{C.RESET}  {tag}")
        print(f"  {C.DIM}agent says:{C.RESET} “{readback}”\n")
        time.sleep(0.4)

    print(f"{C.DIM}Open the dashboard at {base_url}/ to see loads, PODs and the "
          f"discrepancy queue update live.{C.RESET}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate FreightVoice post-delivery calls.")
    ap.add_argument("--base-url", default="http://127.0.0.1:5000")
    args = ap.parse_args()
    return run(args.base_url)


if __name__ == "__main__":
    sys.exit(main())
