"""
Fake TMS service (port 5001).

This stands in for a carrier's Transportation Management System. It is the ONLY
mock in the demo — everything in ``freightvoice/`` is the real production path,
and it talks to this service through an adapter interface that a real Samsara /
Motive integration would implement instead.

It behaves like a real TMS would: loads have lifecycle state
(pending -> delivered -> invoiced), PODs and discrepancies are persisted, and
``GET /state`` exposes the whole world for the live dashboard.

Endpoints
    GET  /loads/<load_id>      -> load context (404 if unknown)
    POST /pod                  -> store POD, mark load delivered
    POST /invoice/<load_id>    -> mark invoiced, return a fake invoice number
    POST /discrepancy          -> append to the discrepancy queue
    POST /reset                -> wipe demo activity and reseed the three loads
    GET  /state                -> dump everything (dashboard + tests)
    GET  /health               -> liveness
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Flask, jsonify, request

from .stores import get_store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app() -> Flask:
    app = Flask(__name__)
    # Storage backend chosen by FAKETMS_STORAGE (sqlite default | insforge).
    store = get_store()
    store.init(reset=True)

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="faketms")

    @app.get("/loads/<load_id>")
    def get_load(load_id: str):
        load = store.get_load(load_id)
        if load is None:
            return jsonify(error="load_not_found", load_id=load_id), 404
        return jsonify(load)

    @app.post("/pod")
    def post_pod():
        body = request.get_json(force=True)
        load_id = body.get("load_id")
        record = body.get("record") or {}
        load = store.get_load(load_id)
        if load is None:
            return jsonify(error="load_not_found", load_id=load_id), 404
        store.save_pod(
            load_id=load_id,
            record_json=record,
            readback=body.get("readback"),
            clean=bool(body.get("clean", False)),
            now=_now(),
        )
        return jsonify(status="stored", load_id=load_id)

    @app.post("/invoice/<load_id>")
    def post_invoice(load_id: str):
        load = store.get_load(load_id)
        if load is None:
            return jsonify(error="load_not_found", load_id=load_id), 404
        # A real TMS returns its own invoice id; we synthesize a believable one.
        invoice_number = f"INV-{load_id}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        store.mark_invoiced(load_id, invoice_number)
        return jsonify(status="invoiced", load_id=load_id, invoice_number=invoice_number)

    @app.post("/discrepancy")
    def post_discrepancy():
        body = request.get_json(force=True)
        load_id = body.get("load_id")
        if store.get_load(load_id) is None:
            return jsonify(error="load_not_found", load_id=load_id), 404
        store.save_discrepancy(
            load_id=load_id,
            code=body.get("code", "unspecified"),
            severity=body.get("severity", "warning"),
            message=body.get("message", ""),
            transcript_excerpt=body.get("transcript_excerpt"),
            now=_now(),
        )
        return jsonify(status="queued", load_id=load_id)

    @app.post("/reset")
    def reset_demo():
        # Route through the storage seam so reset works on any backend.
        store.init(reset=True)
        return jsonify(status="reset", loads=len(store.dump_state()["loads"]))

    @app.get("/state")
    def state():
        return jsonify(store.dump_state())

    return app


if __name__ == "__main__":
    create_app().run(port=5001, debug=False)
