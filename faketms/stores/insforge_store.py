"""
InsForgeStore — fake TMS backed by InsForge (managed Postgres + auto REST API).

This makes the stand-in TMS run on a *real* database: InsForge auto-generates a
PostgREST-style REST API over Postgres, so we treat ``loads`` / ``pods`` /
``discrepancies`` as InsForge tables and hit them over HTTP.

Verified API contract (https://docs.insforge.dev/sdks/rest/database):
    Base URL : https://<app>.insforge.app   (cloud)  |  http://localhost:7130 (self-hosted Docker)
    Auth     : Authorization: Bearer <token>
    Query    : GET    /api/database/records/{table}?col=eq.value&order=col.desc&limit=N
    Create   : POST   /api/database/records/{table}   body: [ {...} ]   header: Prefer: return=representation
    Update   : PATCH  /api/database/records/{table}?col=eq.value   body: {...}
    Delete   : DELETE /api/database/records/{table}?col=eq.value
    Filters  : eq, neq, gt, lt, like, ilike, in  (PostgREST-style)

PREREQUISITE: the three tables must already exist in the InsForge project (create
them via an InsForge migration / the console / MCP — table DDL is not part of the
records REST API). Suggested columns mirror faketms/db.py:
    loads(load_id text pk, shipper, consignee, commodity, expected_pieces int,
          expected_weight_lbs float, scheduled_delivery, equipment_type,
          status default 'pending', invoice_number, delivered_at)
    pods(id bigserial pk, load_id, record_json text, readback, clean bool, created_at)
    discrepancies(id bigserial pk, load_id, code, severity, message,
                  transcript_excerpt, created_at)

The ``session`` arg is injectable so this is unit-testable offline; in production
it defaults to the ``requests`` module.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from ..db import SEED_LOADS
from .base import Store

_RECORDS = "/api/database/records"


class InsForgeStore(Store):
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: float = 10.0, session: Any = None):
        self.base_url = (base_url or os.environ.get(
            "FAKETMS_INSFORGE_URL", "http://localhost:7130")).rstrip("/")
        self.token = token or os.environ.get("FAKETMS_INSFORGE_TOKEN", "")
        self.timeout = timeout
        # ``requests`` and ``requests.Session`` both expose ``.request(...)``.
        self._session = session or requests

    # -- low-level REST helpers -------------------------------------------- #
    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.token}",
             "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    def _url(self, table: str) -> str:
        return f"{self.base_url}{_RECORDS}/{table}"

    def _query(self, table: str, params: dict) -> list[dict]:
        r = self._session.request("GET", self._url(table),
                                  headers=self._headers(), params=params,
                                  timeout=self.timeout)
        r.raise_for_status()
        return r.json() or []

    def _insert(self, table: str, rows: list[dict]) -> None:
        r = self._session.request(
            "POST", self._url(table),
            headers=self._headers({"Prefer": "return=representation"}),
            json=rows, timeout=self.timeout)
        r.raise_for_status()

    def _patch(self, table: str, params: dict, values: dict) -> None:
        r = self._session.request("PATCH", self._url(table),
                                  headers=self._headers(), params=params,
                                  json=values, timeout=self.timeout)
        r.raise_for_status()

    def _delete_all(self, table: str) -> None:
        # PostgREST requires a filter on DELETE; match every row.
        r = self._session.request("DELETE", self._url(table),
                                  headers=self._headers(),
                                  params={"load_id": "not.is.null"}
                                  if table == "loads" else {"id": "not.is.null"},
                                  timeout=self.timeout)
        r.raise_for_status()

    # -- Store interface --------------------------------------------------- #
    def init(self, reset: bool = True) -> None:
        if reset:
            # Children first to respect any FK constraints.
            for table in ("pods", "discrepancies", "loads"):
                self._delete_all(table)
        seed = [dict(load, status="pending") for load in SEED_LOADS]
        self._insert("loads", seed)

    def get_load(self, load_id: str) -> dict[str, Any] | None:
        rows = self._query("loads", {"load_id": f"eq.{load_id}", "limit": 1})
        return rows[0] if rows else None

    def save_pod(self, load_id, record_json, readback, clean, now) -> None:
        self._insert("pods", [{
            "load_id": load_id,
            "record_json": json.dumps(record_json),
            "readback": readback,
            "clean": bool(clean),
            "created_at": now,
        }])
        # Advance to 'delivered' only if still pending — the filter enforces
        # "never downgrade" without a read-modify-write race.
        self._patch("loads",
                    {"load_id": f"eq.{load_id}", "status": "eq.pending"},
                    {"status": "delivered",
                     "delivered_at": record_json.get("delivered_at", now)})

    def mark_invoiced(self, load_id, invoice_number) -> None:
        self._patch("loads", {"load_id": f"eq.{load_id}"},
                    {"status": "invoiced", "invoice_number": invoice_number})

    def save_discrepancy(self, load_id, code, severity, message,
                         transcript_excerpt, now) -> None:
        self._insert("discrepancies", [{
            "load_id": load_id, "code": code, "severity": severity,
            "message": message, "transcript_excerpt": transcript_excerpt,
            "created_at": now,
        }])

    def dump_state(self) -> dict[str, Any]:
        loads = self._query("loads", {"order": "load_id.asc"})
        pods = self._query("pods", {"order": "id.desc"})
        discrepancies = self._query("discrepancies", {"order": "id.desc"})
        for p in pods:
            # Match SqliteStore's dump shape: parsed record + bool clean.
            raw = p.pop("record_json", None)
            p["record"] = json.loads(raw) if raw else {}
            p["clean"] = bool(p.get("clean"))
        return {"loads": loads, "pods": pods, "discrepancies": discrepancies}
