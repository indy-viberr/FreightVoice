"""Schema validation tests — the strict-typing guarantees the agent relies on."""

import pytest
from pydantic import ValidationError

from freightvoice.schemas import (
    AccessorialEvent,
    AccessorialType,
    DeliveryRecord,
    EquipmentType,
    LoadContext,
)


def _valid_load() -> dict:
    return dict(
        load_id="L1001",
        shipper="Acme Foods",
        consignee="Kroger DC #42",
        commodity="Canned goods",
        expected_pieces=20,
        expected_weight_lbs=18000,
        scheduled_delivery="2026-06-19T14:00:00",
        equipment_type="dry_van",
    )


def _valid_record() -> dict:
    return dict(
        load_id="L1001",
        delivered_at="2026-06-19T14:32:00",
        recipient_name="J. Rivera",
        actual_pieces=20,
        actual_weight_lbs=18000,
    )


# --- LoadContext ---------------------------------------------------------- #
def test_load_context_parses_valid():
    load = LoadContext(**_valid_load())
    assert load.load_id == "L1001"
    assert load.equipment_type is EquipmentType.dry_van
    assert load.expected_pieces == 20


def test_load_context_rejects_unknown_equipment():
    bad = _valid_load() | {"equipment_type": "hovercraft"}
    with pytest.raises(ValidationError):
        LoadContext(**bad)


def test_load_context_rejects_negative_weight():
    bad = _valid_load() | {"expected_weight_lbs": -5}
    with pytest.raises(ValidationError):
        LoadContext(**bad)


def test_load_context_rejects_missing_required_field():
    bad = _valid_load()
    del bad["consignee"]
    with pytest.raises(ValidationError):
        LoadContext(**bad)


def test_load_context_rejects_unknown_field():
    bad = _valid_load() | {"trailer_temp": -10}
    with pytest.raises(ValidationError):
        LoadContext(**bad)


# --- AccessorialEvent ----------------------------------------------------- #
def test_accessorial_valid_type():
    acc = AccessorialEvent(type="detention", duration_minutes=120)
    assert acc.type is AccessorialType.detention
    assert acc.duration_minutes == 120
    assert acc.amount_usd is None


def test_accessorial_rejects_unknown_type():
    # The headline guarantee: a hallucinated accessorial cannot reach billing.
    with pytest.raises(ValidationError):
        AccessorialEvent(type="helicopter_lift")


def test_accessorial_rejects_negative_amount():
    with pytest.raises(ValidationError):
        AccessorialEvent(type="lumper", amount_usd=-50)


# --- DeliveryRecord ------------------------------------------------------- #
def test_delivery_record_parses_valid():
    rec = DeliveryRecord(**_valid_record())
    assert rec.load_id == "L1001"
    assert rec.damage is False
    assert rec.accessorials == []


def test_delivery_record_accepts_nested_accessorials():
    rec = DeliveryRecord(
        **_valid_record(),
        accessorials=[{"type": "liftgate"}, {"type": "detention", "duration_minutes": 90}],
    )
    assert len(rec.accessorials) == 2
    assert rec.accessorials[1].duration_minutes == 90


def test_delivery_record_rejects_bad_nested_accessorial():
    with pytest.raises(ValidationError):
        DeliveryRecord(**_valid_record(), accessorials=[{"type": "nope"}])


def test_delivery_record_rejects_negative_pieces():
    bad = _valid_record() | {"actual_pieces": -1}
    with pytest.raises(ValidationError):
        DeliveryRecord(**bad)


def test_delivery_record_rejects_unknown_exception_type():
    bad = _valid_record() | {"exception_type": "abducted_by_aliens"}
    with pytest.raises(ValidationError):
        DeliveryRecord(**bad)


def test_delivery_record_normalizes_vapi_none_exception_sentinel():
    rec = DeliveryRecord(**(_valid_record() | {"exception_type": "none"}))
    assert rec.exception_type is None


def test_delivery_record_blank_recipient_normalized_to_none():
    rec = DeliveryRecord(**(_valid_record() | {"recipient_name": "   "}))
    assert rec.recipient_name is None


def test_delivery_record_rejects_unknown_field():
    bad = _valid_record() | {"signature_image": "base64..."}
    with pytest.raises(ValidationError):
        DeliveryRecord(**bad)


def test_delivery_record_rejects_non_numeric_piece_count():
    bad = _valid_record() | {"actual_pieces": "twenty"}
    with pytest.raises(ValidationError):
        DeliveryRecord(**bad)


def test_delivery_record_rejects_negative_weight():
    bad = _valid_record() | {"actual_weight_lbs": -100}
    with pytest.raises(ValidationError):
        DeliveryRecord(**bad)


def test_delivery_record_accepts_detention_with_duration():
    rec = DeliveryRecord(
        **_valid_record(),
        accessorials=[{"type": "detention", "duration_minutes": 120}],
    )
    assert rec.accessorials[0].duration_minutes == 120
