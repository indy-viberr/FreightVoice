"""
SQLite storage for the fake TMS.

Stdlib ``sqlite3`` only — no ORM. The whole point of this service is to be a
believable, inspectable stand-in for a carrier TMS, so the schema mirrors what a
real load/POD/invoice record looks like and ``dump_state()`` returns the entire
world in one JSON blob for the dashboard.

The DB is rebuilt and reseeded on every boot (``init_db(reset=True)``) so the
demo always starts from a known state across the three discrepancy paths.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

DB_PATH = os.environ.get("FAKETMS_DB", os.path.join(os.path.dirname(__file__), "faketms.sqlite"))


# Three seed loads, each engineered to exercise one discrepancy path when the
# matching delivery record is posted by demo/simulate_call.py:
#   L1001 -> clean        (actuals match expected)
#   L2002 -> weight variance
#   L3003 -> damage + exception
SEED_LOADS: list[dict[str, Any]] = [
    {
        "load_id": "L1001",
        "shipper": "Acme Foods",
        "consignee": "Kroger DC #42",
        "commodity": "Canned goods",
        "expected_pieces": 20,
        "expected_weight_lbs": 18000,
        "scheduled_delivery": "2026-06-19T14:00:00",
        "equipment_type": "dry_van",
    },
    {
        "load_id": "L2002",
        "shipper": "Sunrise Produce",
        "consignee": "Whole Foods DC West",
        "commodity": "Fresh strawberries",
        "expected_pieces": 16,
        "expected_weight_lbs": 14000,
        "scheduled_delivery": "2026-06-19T09:30:00",
        "equipment_type": "reefer",
    },
    {
        "load_id": "L3003",
        "shipper": "Steel Works Inc",
        "consignee": "BuildRite Supply Yard",
        "commodity": "Steel beams",
        "expected_pieces": 8,
        "expected_weight_lbs": 42000,
        "scheduled_delivery": "2026-06-19T11:00:00",
        "equipment_type": "flatbed",
    },
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = True) -> None:
    """Create tables and (re)seed loads. ``reset`` wipes prior demo state."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS loads (
                load_id              TEXT PRIMARY KEY,
                shipper              TEXT NOT NULL,
                consignee            TEXT NOT NULL,
                commodity            TEXT NOT NULL,
                expected_pieces      INTEGER NOT NULL,
                expected_weight_lbs  REAL NOT NULL,
                scheduled_delivery   TEXT NOT NULL,
                equipment_type       TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'pending',
                invoice_number       TEXT,
                delivered_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS pods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                load_id     TEXT NOT NULL REFERENCES loads(load_id),
                record_json TEXT NOT NULL,
                readback    TEXT,
                clean       INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discrepancies (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                load_id            TEXT NOT NULL REFERENCES loads(load_id),
                code               TEXT NOT NULL,
                severity           TEXT NOT NULL,
                message            TEXT NOT NULL,
                transcript_excerpt TEXT,
                created_at         TEXT NOT NULL
            );
            """
        )
        for load in SEED_LOADS:
            conn.execute(
                """
                INSERT OR REPLACE INTO loads
                    (load_id, shipper, consignee, commodity, expected_pieces,
                     expected_weight_lbs, scheduled_delivery, equipment_type, status)
                VALUES (:load_id, :shipper, :consignee, :commodity, :expected_pieces,
                        :expected_weight_lbs, :scheduled_delivery, :equipment_type, 'pending')
                """,
                load,
            )


def get_load(load_id: str) -> dict[str, Any] | None:
    conn = connect()
    row = conn.execute("SELECT * FROM loads WHERE load_id = ?", (load_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_pod(
    load_id: str,
    record_json: dict[str, Any],
    readback: str | None,
    clean: bool,
    now: str,
) -> None:
    """Store a POD and advance the load to 'delivered'.

    Status only moves forward: if the caller already invoiced a clean load
    before writing the POD, we don't downgrade it back to 'delivered'.
    """
    conn = connect()
    with conn:
        conn.execute(
            """INSERT INTO pods (load_id, record_json, readback, clean, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (load_id, json.dumps(record_json), readback, int(clean), now),
        )
        conn.execute(
            """UPDATE loads
                  SET delivered_at = ?,
                      status = CASE WHEN status = 'pending' THEN 'delivered' ELSE status END
                WHERE load_id = ?""",
            (record_json.get("delivered_at", now), load_id),
        )
    conn.close()


def mark_invoiced(load_id: str, invoice_number: str) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE loads SET status = 'invoiced', invoice_number = ? WHERE load_id = ?",
            (invoice_number, load_id),
        )
    conn.close()


def save_discrepancy(
    load_id: str,
    code: str,
    severity: str,
    message: str,
    transcript_excerpt: str | None,
    now: str,
) -> None:
    conn = connect()
    with conn:
        conn.execute(
            """INSERT INTO discrepancies
                   (load_id, code, severity, message, transcript_excerpt, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (load_id, code, severity, message, transcript_excerpt, now),
        )
    conn.close()


def dump_state() -> dict[str, Any]:
    """Everything, for the dashboard and for test assertions."""
    conn = connect()
    loads = [dict(r) for r in conn.execute(
        "SELECT * FROM loads ORDER BY load_id").fetchall()]
    pods = [dict(r) for r in conn.execute(
        "SELECT * FROM pods ORDER BY id DESC").fetchall()]
    discrepancies = [dict(r) for r in conn.execute(
        "SELECT * FROM discrepancies ORDER BY id DESC").fetchall()]
    conn.close()
    # Parse the stored record JSON so consumers don't double-decode.
    for p in pods:
        p["record"] = json.loads(p.pop("record_json"))
        p["clean"] = bool(p["clean"])
    return {"loads": loads, "pods": pods, "discrepancies": discrepancies}
