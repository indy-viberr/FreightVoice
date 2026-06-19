from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request
from pydantic import ValidationError

from freightvoice.adapters.base import AdapterError, FactoringAdapter, LoadNotFoundError, TMSAdapter
from freightvoice.config import Config
from freightvoice.logging_config import log_json
from freightvoice.schemas import (
    DeliveryRecord,
    Discrepancy,
    DiscrepancySeverity,
    LoadContext,
    VapiToolCall,
    VapiToolCallRequest,
    VapiToolCallResponse,
    VapiToolResult,
)
from freightvoice.validation import run_validation


webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhook")
logger = logging.getLogger(__name__)


@webhooks_bp.before_request
def validate_webhook_secret() -> tuple[Response, int] | None:
    config = _config()
    if not config.WEBHOOK_SECRET:
        log_json(logger, logging.WARNING, event="webhook_secret_empty", path=request.path)
        return None

    supplied = request.headers.get("x-vapi-secret")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        supplied = auth_header.removeprefix("Bearer ").strip()
    if supplied != config.WEBHOOK_SECRET:
        log_json(logger, logging.WARNING, event="webhook_auth_failed", path=request.path)
        return jsonify({"error": "unauthorized"}), 401
    return None


@webhooks_bp.post("/get_load_context")
def get_load_context() -> tuple[Response, int] | Response:
    parsed = _first_tool_call()
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[1], int):
        return parsed
    tool_call = parsed
    args = tool_call.function.arguments
    identifier = args.get("load_id") or args.get("pro_number")
    if not identifier:
        return _tool_response(tool_call.id, "I need either a load number or a PRO number to look that up.")

    try:
        context = _tms().get_load(str(identifier))
        result = _format_load_confirmation(context)
        log_json(
            logger,
            logging.INFO,
            event="get_load_context",
            payload=args,
            load_id=context.load_id,
            found=True,
            consignee=context.consignee,
            outcome="returned_context",
        )
        return _tool_response(tool_call.id, result)
    except LoadNotFoundError:
        log_json(
            logger,
            logging.INFO,
            event="get_load_context",
            payload=args,
            load_id=str(identifier),
            found=False,
            outcome="not_found",
        )
        return _tool_response(tool_call.id, f"I couldn't find load {identifier}. Can you read me the number again - slowly?")
    except AdapterError:
        log_json(
            logger,
            logging.ERROR,
            event="get_load_context",
            payload=args,
            load_id=str(identifier),
            found=False,
            outcome="adapter_error",
            exc_info=True,
        )
        return _tool_response(tool_call.id, "I'm having trouble reaching the system. Hang on - I'll transfer you to dispatch.")


@webhooks_bp.post("/push_delivery_record")
def push_delivery_record() -> tuple[Response, int] | Response:
    parsed = _first_tool_call()
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[1], int):
        return parsed
    tool_call = parsed
    args = _delivery_record_args(tool_call.function.arguments)

    try:
        record = DeliveryRecord(**args)
    except ValidationError as exc:
        field = ".".join(str(part) for part in exc.errors()[0]["loc"])
        message = exc.errors()[0]["msg"]
        log_json(
            logger,
            logging.INFO,
            event="push_delivery_record",
            payload=args,
            outcome="validation_error",
            field=field,
            error=message,
        )
        return _tool_response(tool_call.id, f"Validation error on {field}: {message}. Please confirm that detail again.")

    invoice_triggered = False
    advance_triggered = False
    try:
        context = _tms().get_load(record.load_id)
        config = _config()
        validation = run_validation(
            record,
            context,
            weight_variance_pct=config.WEIGHT_VARIANCE_PCT,
            piece_variance_allow=config.PIECE_VARIANCE_ALLOW,
            auto_invoice_below_severity=config.AUTO_INVOICE_BELOW_SEVERITY,
        )
        _tms().write_pod(record)
        if validation.is_clean:
            _tms().trigger_invoice(record.load_id)
            invoice_triggered = True
            _factoring().trigger_advance(record.load_id)
            advance_triggered = True
            result = _format_delivery_summary(record, context, invoice_triggered, advance_triggered)
        else:
            _tms().write_discrepancy(record.load_id, validation.discrepancies)
            result = (
                _format_delivery_summary(record, context, invoice_triggered, advance_triggered)
                + " This has been flagged for your dispatcher to review. You're all set - drive safe."
            )

        log_json(
            logger,
            logging.INFO,
            event="push_delivery_record",
            payload=args,
            load_id=record.load_id,
            is_clean=validation.is_clean,
            discrepancy_count=len(validation.discrepancies),
            invoice_triggered=invoice_triggered,
            advance_triggered=advance_triggered,
            outcome="completed",
        )
        return _tool_response(tool_call.id, result)
    except LoadNotFoundError:
        log_json(
            logger,
            logging.INFO,
            event="push_delivery_record",
            payload=args,
            load_id=record.load_id,
            outcome="load_not_found",
        )
        return _tool_response(tool_call.id, f"I couldn't find load {record.load_id}. Can you read me the number again - slowly?")
    except AdapterError:
        log_json(
            logger,
            logging.ERROR,
            event="push_delivery_record",
            payload=args,
            load_id=record.load_id,
            outcome="adapter_error",
            exc_info=True,
        )
        return _tool_response(tool_call.id, "I'm having trouble reaching the system. Hang on - I'll transfer you to dispatch.")


@webhooks_bp.post("/flag_discrepancy")
def flag_discrepancy() -> tuple[Response, int] | Response:
    parsed = _first_tool_call()
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[1], int):
        return parsed
    tool_call = parsed
    args = tool_call.function.arguments
    load_id = str(args.get("load_id", ""))
    description = str(args.get("description", ""))
    transcript_excerpt = args.get("transcript_excerpt")
    if not load_id or not description:
        return _tool_response(tool_call.id, "I need the load number and a short description to flag that.")

    discrepancy = Discrepancy(
        trigger="manual_flag",
        severity=DiscrepancySeverity.WARNING,
        message=description,
        detail={"transcript_excerpt": transcript_excerpt} if transcript_excerpt else {},
    )
    try:
        _tms().write_discrepancy(load_id, [discrepancy])
        log_json(
            logger,
            logging.INFO,
            event="flag_discrepancy",
            payload=args,
            load_id=load_id,
            outcome="queued",
        )
        return _tool_response(tool_call.id, f"Flagged. Your dispatcher will follow up. Call reference: {load_id}.")
    except AdapterError:
        log_json(
            logger,
            logging.ERROR,
            event="flag_discrepancy",
            payload=args,
            load_id=load_id,
            outcome="adapter_error",
            exc_info=True,
        )
        return _tool_response(tool_call.id, "I'm having trouble reaching the system. Hang on - I'll transfer you to dispatch.")


@webhooks_bp.post("/schedule_callback")
def schedule_callback() -> tuple[Response, int] | Response:
    parsed = _first_tool_call()
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[1], int):
        return parsed
    tool_call = parsed
    args = tool_call.function.arguments
    load_id = str(args.get("load_id", ""))
    if not load_id:
        return _tool_response(tool_call.id, "I need the load number to schedule that callback.")

    try:
        schedule = getattr(_tms(), "schedule_callback")
        schedule(load_id, args.get("driver_phone"), args.get("reason"))
        log_json(
            logger,
            logging.INFO,
            event="schedule_callback",
            payload=args,
            load_id=load_id,
            outcome="scheduled",
        )
        return _tool_response(tool_call.id, f"Got it. Someone will call you back shortly about load {load_id}.")
    except (AdapterError, AttributeError):
        log_json(
            logger,
            logging.ERROR,
            event="schedule_callback",
            payload=args,
            load_id=load_id,
            outcome="adapter_error",
            exc_info=True,
        )
        return _tool_response(tool_call.id, "I'm having trouble reaching the system. Hang on - I'll transfer you to dispatch.")


def _first_tool_call() -> VapiToolCall | tuple[Response, int]:
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "malformed JSON body"}), 400
    try:
        envelope = VapiToolCallRequest(**payload)
        tool_calls = envelope.get_tool_calls()
    except ValidationError as exc:
        log_json(logger, logging.INFO, event="malformed_envelope", payload=payload, error=exc.errors())
        return jsonify({"error": "malformed Vapi tool call envelope"}), 400

    if not tool_calls:
        log_json(logger, logging.INFO, event="malformed_envelope", payload=payload, error="no toolCalls")
        return jsonify({"error": "Vapi envelope contained no tool calls"}), 400
    return tool_calls[0]


def _tool_response(tool_call_id: str, result: str, status: int = 200) -> tuple[Response, int]:
    payload = VapiToolCallResponse(results=[VapiToolResult(toolCallId=tool_call_id, result=result)])
    return jsonify(payload.model_dump(mode="json")), status


def _delivery_record_args(args: dict[str, object]) -> dict[str, object]:
    for key in ("record", "delivery_record", "DeliveryRecord"):
        nested = args.get(key)
        if isinstance(nested, dict):
            return nested
    return args


def _format_load_confirmation(context: LoadContext) -> str:
    equipment = context.equipment_type.value.replace("_", " ")
    return (
        f"Got it. Load {context.load_id} - {context.expected_pieces} pallets of {context.commodity}, "
        f"{equipment}, from {context.origin_city} to {context.consignee} in {context.destination_city}. "
        "Scheduled delivery today. Does that sound right?"
    )


def _format_delivery_summary(
    record: DeliveryRecord,
    context: LoadContext,
    invoice_triggered: bool,
    advance_triggered: bool,
) -> str:
    delivered_time = _format_time(record.delivered_at)
    pieces_label = "pallet" if record.actual_pieces == 1 else "pallets"
    damage_text = f"Damage reported: {_sentence(record.damage_notes)}" if record.damage else "No damage."
    accessorial_text = _format_accessorials(record)
    summary = (
        f"Confirmed. Load {record.load_id} delivered at {delivered_time} to {record.recipient_name} "
        f"at {context.consignee}. {record.actual_pieces} {pieces_label}, "
        f"{record.actual_weight_lbs:,.0f} pounds. {damage_text}"
    )
    if accessorial_text:
        summary += f" {accessorial_text}"
    if invoice_triggered:
        summary += " Invoice submitted."
    if advance_triggered:
        summary += " Your factoring advance is on the way."
    return summary


def _format_accessorials(record: DeliveryRecord) -> str:
    parts: list[str] = []
    for item in record.accessorials:
        label = item.type.value.replace("_", " ").title()
        if item.duration_minutes is not None:
            hours, minutes = divmod(item.duration_minutes, 60)
            if hours and minutes:
                duration = f"{hours} hours {minutes} minutes"
            elif hours:
                duration = f"{hours} hours"
            else:
                duration = f"{minutes} minutes"
            parts.append(f"{label} noted - {duration}.")
        elif item.amount_usd is not None:
            parts.append(f"{label} noted - ${item.amount_usd:,.2f}.")
        else:
            parts.append(f"{label} noted.")
    return " ".join(parts)


def _sentence(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return text if text[-1] in ".!?" else f"{text}."


def _format_time(value: datetime) -> str:
    hour = value.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{value.strftime('%M %p')}"


def _config() -> Config:
    return current_app.config["APP_CONFIG"]


def _tms() -> TMSAdapter:
    return current_app.extensions["tms_adapter"]


def _factoring() -> FactoringAdapter:
    return current_app.extensions["factoring_adapter"]
