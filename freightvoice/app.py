"""
FreightVoice middleware (port 5000) — the Vapi-facing webhook product.

This is the real, production path. Vapi runs the voice call and invokes these
four webhooks as server tools:

  POST /webhook/get_load_context    — pull load context so the agent confirms,
                                      not dictates.
  POST /webhook/push_delivery_record— validate -> run discrepancy engine ->
                                      write POD -> invoice (if clean) -> advance.
  POST /webhook/flag_discrepancy    — explicit escalation to the exception queue.
  POST /webhook/schedule_callback   — record a callback intent (driver dropped).

Plus the live dashboard:
  GET  /                            — projector view (static SPA).
  GET  /api/state                   — merged TMS + middleware state, polled 2s.

Every webhook logs its inbound payload and the decision it took; that log is the
demo narrative, and it's also surfaced on the dashboard's activity feed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory
from pydantic import ValidationError

from . import config, security, store
from .adapters import LoadNotFound, get_factoring_adapter, get_tms_adapter
from .schemas import DeliveryRecord, normalize_load_id
from .validation import DiscrepancyConfig, evaluate, is_clean
from .vapi import ToolCall, parse_tool_calls, results_envelope

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger("freightvoice")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_calls_or_error():
    """Parse the inbound body into tool calls, or return a controlled 400.

    ``silent=True`` makes malformed JSON return ``None`` instead of throwing
    werkzeug's default HTML 400 — so a bad body yields a clean JSON error the
    agent/caller can handle, not a stack trace.
    """
    body = request.get_json(force=True, silent=True)
    if body is None:
        log.warning("[webhook] rejected: body was not valid JSON")
        return None, (jsonify(error="invalid_json",
                              message="Request body was not valid JSON."), 400)
    return parse_tool_calls(body), None


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    tms = get_tms_adapter()
    factoring = get_factoring_adapter()
    disc_config = DiscrepancyConfig(weight_tolerance_pct=config.WEIGHT_TOLERANCE_PCT)

    log.info("FreightVoice up — TMS backend=%s, weight tolerance=%.0f%%, webhook auth=%s",
             config.TMS_BACKEND, config.WEIGHT_TOLERANCE_PCT,
             f"{config.VAPI_AUTH_MODE} (on)" if security.is_enabled() else "off")

    @app.before_request
    def _authenticate_webhooks():
        # Guard only the Vapi-facing webhooks; dashboard/health stay open.
        if not request.path.startswith("/webhook/"):
            return None
        ok, reason = security.verify(request.headers, request.get_data())
        if not ok:
            log.warning("[auth] rejected %s: %s", request.path, reason)
            return jsonify(error="unauthorized", message=reason), 401
        return None

    # ------------------------------------------------------------------ #
    # Webhook: get_load_context
    # ------------------------------------------------------------------ #
    @app.post("/webhook/get_load_context")
    def get_load_context():
        calls, err = _tool_calls_or_error()
        if err:
            return err
        results = []
        for call in calls:
            load_id = normalize_load_id(
                call.arguments.get("load_id")
                or call.arguments.get("pro_number")
                or ""
            )
            log.info("[get_load_context] inbound load_id=%r", load_id)

            if not load_id:
                store.log_decision(_now(), "get_load_context",
                                   "No load id provided by agent.", "warning")
                results.append((call.id, {
                    "found": False,
                    "message": "No load number was provided. Ask the driver to read "
                               "the PRO or load number.",
                }))
                continue

            try:
                load = tms.get_load(load_id)
            except LoadNotFound:
                # 404 -> tell the agent so it asks the driver to re-read it.
                log.info("[get_load_context] load %s not found", load_id)
                store.log_decision(_now(), "get_load_context",
                                   f"Load {load_id} not found — agent will re-ask.",
                                   "warning", load_id)
                results.append((call.id, {
                    "found": False,
                    "message": f"No load found for {load_id}. Politely ask the driver "
                               f"to re-read the load or PRO number, digit by digit.",
                }))
                continue

            store.log_decision(_now(), "get_load_context",
                               f"Fetched {load_id}: {load.shipper} → {load.consignee}.",
                               "info", load_id)
            results.append((call.id, {
                "found": True,
                "load": load.model_dump(mode="json"),
            }))
        return jsonify(results_envelope(results))

    # ------------------------------------------------------------------ #
    # Webhook: push_delivery_record  (the main event)
    # ------------------------------------------------------------------ #
    @app.post("/webhook/push_delivery_record")
    def push_delivery_record():
        calls, err = _tool_calls_or_error()
        if err:
            return err
        results = []
        for call in calls:
            results.append((call.id, _handle_push(call, tms, factoring, disc_config)))
        return jsonify(results_envelope(results))

    # ------------------------------------------------------------------ #
    # Webhook: flag_discrepancy  (explicit escalation)
    # ------------------------------------------------------------------ #
    @app.post("/webhook/flag_discrepancy")
    def flag_discrepancy():
        from .validation import Discrepancy, DiscrepancyCode, Severity

        calls, err = _tool_calls_or_error()
        if err:
            return err
        results = []
        for call in calls:
            a = call.arguments
            load_id = normalize_load_id(a.get("load_id") or "")
            reason = a.get("reason") or a.get("message") or "Driver-reported issue"
            severity = (a.get("severity") or "warning").lower()
            excerpt = a.get("transcript_excerpt")
            log.info("[flag_discrepancy] load=%s reason=%r severity=%s",
                     load_id, reason, severity)

            if not load_id:
                results.append((call.id, "I need the load number to flag this."))
                continue

            try:
                sev = Severity(severity)
            except ValueError:
                sev = Severity.warning
            disc = Discrepancy(code=DiscrepancyCode.exception, severity=sev, message=reason)
            try:
                tms.write_discrepancy(load_id, disc, excerpt)
            except LoadNotFound:
                results.append((call.id, f"No load found for {load_id} to flag against."))
                continue

            store.log_decision(_now(), "flag_discrepancy",
                               f"Escalated {load_id}: {reason} [{sev.value}].",
                               sev.value if sev.value in ("warning", "critical") else "warning",
                               load_id)
            results.append((call.id,
                            f"Flagged load {load_id} for review and noted it for the team."))
        return jsonify(results_envelope(results))

    # ------------------------------------------------------------------ #
    # Webhook: schedule_callback  (stub — records intent, no real dialing)
    # ------------------------------------------------------------------ #
    @app.post("/webhook/schedule_callback")
    def schedule_callback():
        calls, err = _tool_calls_or_error()
        if err:
            return err
        results = []
        for call in calls:
            a = call.arguments
            load_id = normalize_load_id(a.get("load_id") or "") or None
            reason = a.get("reason") or "Driver disconnected"
            phone = a.get("phone") or a.get("callback_number")
            log.info("[schedule_callback] load=%s phone=%s reason=%r",
                     load_id, phone, reason)
            store.add_callback(load_id, reason, phone, _now())
            store.log_decision(_now(), "schedule_callback",
                               f"Callback queued{f' for {load_id}' if load_id else ''}: {reason}.",
                               "info", load_id)
            results.append((call.id,
                            "Okay, I've scheduled a callback. We'll reach back out shortly."))
        return jsonify(results_envelope(results))

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #
    @app.get("/")
    def dashboard():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def api_state():
        """Merged view: TMS world + middleware (callbacks, decision log)."""
        tms_state = {"loads": [], "pods": [], "discrepancies": [], "tms_error": None}
        try:
            resp = requests.get(f"{config.FAKETMS_URL}/state", timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            tms_state.update(resp.json())
        except requests.RequestException as e:
            tms_state["tms_error"] = str(e)
        tms_state.update(store.snapshot())
        tms_state["backend"] = config.TMS_BACKEND
        return jsonify(tms_state)

    @app.get("/health")
    def health():
        return jsonify(status="ok", service="freightvoice", backend=config.TMS_BACKEND)

    return app


# ---------------------------------------------------------------------- #
# push_delivery_record core logic, factored out for readability + testing.
# ---------------------------------------------------------------------- #
def _handle_push(call: ToolCall, tms, factoring, disc_config: DiscrepancyConfig):
    log.info("[push_delivery_record] inbound: %s", call.arguments)

    # 1. Validate the record. A schema error goes back to the agent to re-ask.
    try:
        record = DeliveryRecord(**call.arguments)
    except ValidationError as e:
        fields = ", ".join(str(err["loc"][-1]) for err in e.errors())
        log.warning("[push_delivery_record] validation failed: %s", fields)
        store.log_decision(_now(), "push_delivery_record",
                           f"Rejected delivery record — invalid fields: {fields}.", "warning")
        return (f"I couldn't record that — the details for {fields} didn't look right. "
                f"Let's go over them again.")

    # 2. Fetch the load it refers to.
    try:
        load = tms.get_load(record.load_id)
    except LoadNotFound:
        store.log_decision(_now(), "push_delivery_record",
                           f"Load {record.load_id} not found on delivery push.",
                           "warning", record.load_id)
        return (f"I don't have load {record.load_id} on file. Can you re-read "
                f"the load number for me?")

    # 3. Run the discrepancy engine.
    discrepancies = evaluate(record, load, disc_config)
    clean = is_clean(discrepancies)

    # 4. Persist each discrepancy to the exception queue (severity preserved).
    for d in discrepancies:
        tms.write_discrepancy(record.load_id, d, record.transcript_excerpt)

    # 5. Clean -> invoice (+ optional factoring advance). Dirty -> hold.
    #    Invoicing before the POD write is fine: faketms only advances status
    #    forward, so the subsequent write_pod won't downgrade an invoiced load.
    if clean:
        invoice_number = tms.trigger_invoice(record.load_id)
        advance_ref = factoring.trigger_advance(record.load_id)
        readback = _clean_readback(record, load, invoice_number, advance_ref)
        store.log_decision(_now(), "push_delivery_record",
                           f"{record.load_id} clean → invoiced {invoice_number}"
                           + (f", advance {advance_ref}" if advance_ref else "") + ".",
                           "success", record.load_id)
    else:
        worst = max(discrepancies, key=lambda d: _SEV_RANK[d.severity.value])
        readback = _flagged_readback(record, discrepancies)
        store.log_decision(_now(), "push_delivery_record",
                           f"{record.load_id} held — {len(discrepancies)} discrepancy(ies): "
                           + "; ".join(d.code.value for d in discrepancies) + ".",
                           worst.severity.value if worst.severity.value != "info" else "warning",
                           record.load_id)

    # 6. Write the POD exactly once, with the spoken readback attached.
    tms.write_pod(record, readback=readback, clean=clean)
    return readback


_SEV_RANK = {"info": 0, "warning": 1, "critical": 2}


def _clean_readback(record: DeliveryRecord, load, invoice_number: str,
                    advance_ref: str) -> str:
    parts = [
        f"Got it — load {record.load_id} delivered to {load.consignee}",
        f"with all {record.actual_pieces} pieces",
    ]
    if record.recipient_name:
        parts.append(f"signed for by {record.recipient_name}")
    line = ", ".join(parts) + "."
    line += f" Everything checks out, so I've sent it to billing as {invoice_number}."
    return line


def _flagged_readback(record: DeliveryRecord, discrepancies) -> str:
    issues = "; ".join(d.message for d in discrepancies)
    return (f"Thanks — I've logged the delivery for load {record.load_id}, but I'm "
            f"flagging it for our team to review: {issues} "
            f"We won't bill it until someone takes a look.")


app = None

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "5000"))
    create_app().run(host="0.0.0.0", port=port, debug=False)
