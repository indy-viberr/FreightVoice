from __future__ import annotations

from datetime import datetime, timezone

from freightvoice.schemas import DeliveryRecord, DiscrepancySeverity, EquipmentType, ExceptionType, LoadContext
from freightvoice.validation import run_validation


def context() -> LoadContext:
    return LoadContext(
        load_id="FV-DEMO-TEST",
        pro_number="PRO-TEST",
        shipper="Acme Foods",
        consignee="XYZ Distribution",
        origin_city="Memphis",
        destination_city="Atlanta",
        commodity="dry goods",
        expected_pieces=24,
        expected_weight_lbs=10000,
        scheduled_delivery=datetime(2026, 6, 19, 20, 0, tzinfo=timezone.utc),
        equipment_type=EquipmentType.DRY_VAN,
    )


def record(**overrides: object) -> DeliveryRecord:
    data: dict[str, object] = {
        "load_id": "FV-DEMO-TEST",
        "delivered_at": "2026-06-19T20:14:00Z",
        "recipient_name": "Jane Smith",
        "actual_pieces": 24,
        "actual_weight_lbs": 10000,
        "damage": False,
        "accessorials": [],
    }
    data.update(overrides)
    return DeliveryRecord(**data)


def triggers(result: object) -> set[str]:
    return {item.trigger for item in result.discrepancies}


def test_clean_record_passes() -> None:
    result = run_validation(record(), context())
    assert result.is_clean is True
    assert result.discrepancies == []


def test_weight_variance_warning() -> None:
    result = run_validation(record(actual_weight_lbs=10600), context())
    assert result.discrepancies[0].trigger == "weight_variance"
    assert result.discrepancies[0].severity == DiscrepancySeverity.WARNING
    assert result.is_clean is False


def test_weight_variance_critical() -> None:
    result = run_validation(record(actual_weight_lbs=12000), context())
    assert result.discrepancies[0].trigger == "weight_variance"
    assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL


def test_piece_short_flags() -> None:
    result = run_validation(record(actual_pieces=22), context())
    assert result.discrepancies[0].trigger == "piece_short"
    assert result.discrepancies[0].severity == DiscrepancySeverity.WARNING


def test_piece_overage_info() -> None:
    result = run_validation(record(actual_pieces=25), context())
    assert result.discrepancies[0].trigger == "piece_overage"
    assert result.discrepancies[0].severity == DiscrepancySeverity.INFO
    assert result.is_clean is True


def test_damage_is_critical() -> None:
    result = run_validation(record(damage=True, damage_notes="Crushed corner"), context())
    assert result.discrepancies[0].trigger == "damage_reported"
    assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL


def test_refused_is_critical() -> None:
    result = run_validation(record(exception_type=ExceptionType.REFUSED), context())
    assert result.discrepancies[0].trigger == "exception_refused"
    assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL


def test_missing_recipient_is_critical() -> None:
    result = run_validation(record(recipient_name=""), context())
    assert result.discrepancies[0].trigger == "missing_recipient"
    assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL


def test_multiple_triggers_independent() -> None:
    result = run_validation(record(damage=True, damage_notes="Broken wrap", actual_weight_lbs=12000), context())
    assert {"damage_reported", "weight_variance"} <= triggers(result)


def test_severity_per_trigger_not_universal() -> None:
    result = run_validation(
        record(damage=True, damage_notes="Broken wrap", actual_weight_lbs=12000, actual_pieces=25),
        context(),
    )
    severities = {item.trigger: item.severity for item in result.discrepancies}
    assert severities["damage_reported"] == DiscrepancySeverity.CRITICAL
    assert severities["weight_variance"] == DiscrepancySeverity.CRITICAL
    assert severities["piece_overage"] == DiscrepancySeverity.INFO

