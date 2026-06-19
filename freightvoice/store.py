"""
Small in-process store for state that lives in the middleware, not the TMS.

Two things belong here:

* **callback intents** — when a driver disconnects, ``schedule_callback`` records
  the intent to call them back. There's no real outbound dialing; this is a
  queue a human (or a later automation) drains. It is middleware state, not a
  carrier record, so it doesn't go through the TMS adapter.
* **decision log** — a readable, append-only narrative of what each webhook
  decided. This is the demo's story on the projector: "load fetched", "clean ->
  invoiced INV-...", "damage -> flagged critical". Capped to recent entries.

In-memory is deliberate: the demo is a single process and resets cleanly on
reboot, same as the seeded fake TMS.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

_lock = threading.Lock()
_callbacks: list[dict[str, Any]] = []
_decisions: deque[dict[str, Any]] = deque(maxlen=50)


def add_callback(load_id: str | None, reason: str | None, phone: str | None,
                 when: str) -> dict[str, Any]:
    entry = {
        "load_id": load_id,
        "reason": reason,
        "phone": phone,
        "created_at": when,
        "status": "pending",
    }
    with _lock:
        _callbacks.append(entry)
    return entry


def log_decision(when: str, endpoint: str, summary: str,
                 level: str = "info", load_id: str | None = None) -> None:
    """Append a human-readable decision. ``level`` in info|warning|critical|success."""
    with _lock:
        _decisions.appendleft({
            "created_at": when,
            "endpoint": endpoint,
            "summary": summary,
            "level": level,
            "load_id": load_id,
        })


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "callbacks": list(_callbacks),
            "decisions": list(_decisions),
        }


def reset() -> None:
    """Test helper."""
    with _lock:
        _callbacks.clear()
        _decisions.clear()
