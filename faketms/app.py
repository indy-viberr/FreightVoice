from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import cast

from flask import Flask, Response, jsonify, request
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from faketms.models import Base, Callback, DiscrepancyRecord, Invoice, Load, Pod
from faketms.seed import seed_database
from freightvoice.schemas import DeliveryRecord, Discrepancy, LoadContext


def create_app(config_override: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)
    database_url = os.getenv("FAKETMS_DATABASE_URL", "sqlite:///faketms.sqlite3")
    if config_override:
        database_url = cast(str, config_override.get("FAKETMS_DATABASE_URL", database_url))
        database_url = cast(str, config_override.get("DATABASE_URL", database_url))

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    seed_database(SessionLocal)

    app.config["SESSION_FACTORY"] = SessionLocal

    @app.get("/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    @app.get("/loads/<identifier>")
    def get_load(identifier: str) -> Response:
        with _session(app) as session:
            load = _find_load(session, identifier)
            if load is None:
                return jsonify({"error": f"load {identifier} not found"}), 404
            return jsonify(_load_to_context(load).model_dump(mode="json"))

    @app.post("/pod")
    def write_pod() -> Response:
        payload = request.get_json(silent=True) or {}
        try:
            record = DeliveryRecord(**payload)
        except ValidationError as exc:
            return jsonify({"error": exc.errors()}), 400

        with _session(app) as session:
            load = session.get(Load, record.load_id)
            if load is None:
                return jsonify({"error": f"load {record.load_id} not found"}), 404

            pod = session.scalar(select(Pod).where(Pod.load_id == record.load_id))
            if pod is None:
                pod = Pod(load_id=record.load_id)
                session.add(pod)

            pod.delivered_at = record.delivered_at
            pod.recipient_name = record.recipient_name
            pod.actual_pieces = record.actual_pieces
            pod.actual_weight_lbs = record.actual_weight_lbs
            pod.damage = record.damage
            pod.damage_notes = record.damage_notes
            pod.accessorials_json = [item.model_dump(mode="json") for item in record.accessorials]
            pod.exception_type = record.exception_type.value if record.exception_type else None
            pod.transcript_excerpt = record.transcript_excerpt
            if load.status != "invoiced":
                load.status = "delivered"
            session.commit()
            return jsonify({"status": "stored", "load_id": record.load_id})

    @app.post("/invoice/<load_id>")
    def trigger_invoice(load_id: str) -> Response:
        with _session(app) as session:
            load = session.get(Load, load_id)
            if load is None:
                return jsonify({"error": f"load {load_id} not found"}), 404
            invoice = session.scalar(select(Invoice).where(Invoice.load_id == load_id))
            if invoice is None:
                invoice = Invoice(load_id=load_id, invoice_number=f"INV-{load_id}")
                session.add(invoice)
            load.status = "invoiced"
            session.commit()
            return jsonify({"invoice_number": invoice.invoice_number})

    @app.post("/discrepancy")
    def write_discrepancy() -> Response:
        payload = request.get_json(silent=True) or {}
        load_id = str(payload.get("load_id", ""))
        if not load_id:
            return jsonify({"error": "load_id required"}), 400

        raw_discrepancies = payload.get("discrepancies_json", payload.get("discrepancies", []))
        if isinstance(raw_discrepancies, dict):
            raw_discrepancies = [raw_discrepancies]

        with _session(app) as session:
            if session.get(Load, load_id) is None:
                return jsonify({"error": f"load {load_id} not found"}), 404
            for raw in raw_discrepancies:
                discrepancy = Discrepancy(**raw)
                session.add(
                    DiscrepancyRecord(
                        load_id=load_id,
                        trigger=discrepancy.trigger,
                        severity=discrepancy.severity.value,
                        message=discrepancy.message,
                        detail_json=discrepancy.detail,
                        transcript_excerpt=payload.get("transcript_excerpt"),
                    )
                )
            session.commit()
            return jsonify({"status": "queued", "count": len(raw_discrepancies)})

    @app.post("/callback")
    def schedule_callback() -> Response:
        payload = request.get_json(silent=True) or {}
        load_id = str(payload.get("load_id", ""))
        if not load_id:
            return jsonify({"error": "load_id required"}), 400
        with _session(app) as session:
            if session.get(Load, load_id) is None:
                return jsonify({"error": f"load {load_id} not found"}), 404
            callback = Callback(
                load_id=load_id,
                driver_phone=payload.get("driver_phone"),
                reason=payload.get("reason"),
            )
            session.add(callback)
            session.commit()
            return jsonify({"status": "scheduled", "id": callback.id})

    @app.get("/state")
    def state() -> Response:
        with _session(app) as session:
            loads = list(session.scalars(select(Load).order_by(Load.id)))
            pods = list(session.scalars(select(Pod).order_by(Pod.id)))
            invoices = list(session.scalars(select(Invoice).order_by(Invoice.id)))
            discrepancies = list(session.scalars(select(DiscrepancyRecord).order_by(DiscrepancyRecord.id)))
            callbacks = list(session.scalars(select(Callback).order_by(Callback.id)))
            flagged_loads = {item.load_id for item in discrepancies if not item.resolved}
            return jsonify(
                {
                    "loads": [_load_to_dict(load, load.id in flagged_loads) for load in loads],
                    "pods": [_pod_to_dict(pod) for pod in pods],
                    "invoices": [_invoice_to_dict(invoice) for invoice in invoices],
                    "discrepancies": [_discrepancy_to_dict(item) for item in discrepancies],
                    "callbacks": [_callback_to_dict(callback) for callback in callbacks],
                }
            )

    return app


def _session(app: Flask) -> Session:
    return cast(sessionmaker[Session], app.config["SESSION_FACTORY"])()


def _find_load(session: Session, identifier: str) -> Load | None:
    load = session.get(Load, identifier)
    if load is not None:
        return load
    return session.scalar(select(Load).where(Load.pro_number == identifier))


def _load_to_context(load: Load) -> LoadContext:
    return LoadContext(
        load_id=load.id,
        pro_number=load.pro_number,
        shipper=load.shipper,
        consignee=load.consignee,
        origin_city=load.origin_city,
        destination_city=load.destination_city,
        commodity=load.commodity,
        expected_pieces=load.expected_pieces,
        expected_weight_lbs=load.expected_weight_lbs,
        scheduled_delivery=load.scheduled_delivery,
        equipment_type=load.equipment_type,
        notes=load.notes,
    )


def _load_to_dict(load: Load, flagged: bool) -> dict[str, object]:
    return _load_to_context(load).model_dump(mode="json") | {
        "status": load.status,
        "display_status": "flagged" if flagged and load.status != "invoiced" else load.status,
        "has_open_discrepancy": flagged,
    }


def _pod_to_dict(pod: Pod) -> dict[str, object]:
    summary_damage = "Damage reported" if pod.damage else "No damage"
    return {
        "id": pod.id,
        "load_id": pod.load_id,
        "delivered_at": _iso(pod.delivered_at),
        "recipient_name": pod.recipient_name,
        "actual_pieces": pod.actual_pieces,
        "actual_weight_lbs": pod.actual_weight_lbs,
        "damage": pod.damage,
        "damage_notes": pod.damage_notes,
        "accessorials": pod.accessorials_json,
        "exception_type": pod.exception_type,
        "transcript_excerpt": pod.transcript_excerpt,
        "created_at": _iso(pod.created_at),
        "readback_summary": (
            f"Load {pod.load_id} delivered to {pod.recipient_name}: "
            f"{pod.actual_pieces} pieces, {pod.actual_weight_lbs:,.0f} lbs. {summary_damage}."
        ),
    }


def _invoice_to_dict(invoice: Invoice) -> dict[str, object]:
    return {
        "id": invoice.id,
        "load_id": invoice.load_id,
        "invoice_number": invoice.invoice_number,
        "created_at": _iso(invoice.created_at),
    }


def _discrepancy_to_dict(item: DiscrepancyRecord) -> dict[str, object]:
    return {
        "id": item.id,
        "load_id": item.load_id,
        "trigger": item.trigger,
        "severity": item.severity,
        "message": item.message,
        "detail": item.detail_json,
        "transcript_excerpt": item.transcript_excerpt,
        "created_at": _iso(item.created_at),
        "resolved": item.resolved,
    }


def _callback_to_dict(callback: Callback) -> dict[str, object]:
    return {
        "id": callback.id,
        "load_id": callback.load_id,
        "driver_phone": callback.driver_phone,
        "reason": callback.reason,
        "created_at": _iso(callback.created_at),
    }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("FAKETMS_PORT", "5001")))
