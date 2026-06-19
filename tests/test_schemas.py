from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from freightvoice.schemas import (
    AccessorialEvent,
    DeliveryRecord,
    EquipmentType,
    LoadContext,
)


def valid_record_data() -> dict[str, object]:
    return {
        "load_id": "FV-DEMO-001",
        "delivered_at": "2026-06-19T20:14:00Z",
        "recipient_name": "Jane Smith",
        "actual_pieces": 24,
        "actual_weight_lbs": 18400,
        "damage": False,
        "accessorials": [],
    }


def test_delivery_record_valid() -> None:
    record = DeliveryRecord(**valid_record_data())
    assert record.load_id == "FV-DEMO-001"


def test_delivery_record_damage_requires_notes() -> None:
    data = valid_record_data() | {"damage": True, "damage_notes": None}
    with pytest.raises(ValidationError):
        DeliveryRecord(**data)


def test_accessorial_detention_requires_duration() -> None:
    with pytest.raises(ValidationError):
        AccessorialEvent(type="detention")


def test_accessorial_lumper_requires_amount() -> None:
    with pytest.raises(ValidationError):
        AccessorialEvent(type="lumper")


def test_unknown_accessorial_type_rejected() -> None:
    with pytest.raises(ValidationError):
        AccessorialEvent(type="pizza_delivery")


def test_extra_fields_rejected() -> None:
    data = valid_record_data() | {"unexpected": "nope"}
    with pytest.raises(ValidationError):
        DeliveryRecord(**data)


def test_load_context_roundtrip() -> None:
    context = LoadContext(
        load_id="FV-DEMO-001",
        pro_number="PRO-001",
        shipper="Acme Foods",
        consignee="XYZ Distribution Atlanta",
        origin_city="Memphis",
        destination_city="Atlanta",
        commodity="dry goods",
        expected_pieces=24,
        expected_weight_lbs=18400,
        scheduled_delivery=datetime(2026, 6, 19, 20, 0, tzinfo=timezone.utc),
        equipment_type=EquipmentType.DRY_VAN,
        notes="Dock 4",
    )
    payload = context.model_dump(mode="json")
    assert LoadContext(**payload) == context

