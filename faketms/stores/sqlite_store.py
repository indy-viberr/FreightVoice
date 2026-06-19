"""SqliteStore — the zero-config demo default.

Delegates to ``faketms.db`` (stdlib sqlite3). This is intentionally a thin
wrapper: ``db.py`` already holds the canonical schema and seed, and keeping it
untouched means the SQLite path behaves exactly as before the storage seam
existed.
"""

from __future__ import annotations

from typing import Any

from .. import db
from .base import Store


class SqliteStore(Store):
    def init(self, reset: bool = True) -> None:
        db.init_db(reset=reset)

    def get_load(self, load_id: str) -> dict[str, Any] | None:
        return db.get_load(load_id)

    def save_pod(self, load_id, record_json, readback, clean, now) -> None:
        db.save_pod(load_id=load_id, record_json=record_json,
                    readback=readback, clean=clean, now=now)

    def mark_invoiced(self, load_id, invoice_number) -> None:
        db.mark_invoiced(load_id, invoice_number)

    def save_discrepancy(self, load_id, code, severity, message,
                         transcript_excerpt, now) -> None:
        db.save_discrepancy(load_id=load_id, code=code, severity=severity,
                            message=message, transcript_excerpt=transcript_excerpt,
                            now=now)

    def dump_state(self) -> dict[str, Any]:
        return db.dump_state()
