"""Discrepancy engine tests — one per trigger, severity checked per trigger."""

from freightvoice.schemas import DeliveryRecord, LoadContext
from freightvoice.validation import (
    DiscrepancyCode,
    DiscrepancyConfig,
    Severity,
    evaluate,
    is_clean,
)


def make_load(**over) -> LoadContext:
    base = dict(
        load_id="L1001",
        shipper="Acme Foods",
        consignee="Kroger DC #42",
        commodity="Canned goods",
        expected_pieces=20,
        expected_weight_lbs=18000,
        scheduled_delivery="2026-06-19T14:00:00",
        equipment_type="dry_van",
    )
    return LoadContext(**(base | over))


def make_record(**over) -> DeliveryRecord:
    base = dict(
        load_id="L1001",
        delivered_at="2026-06-19T14:32:00",
        recipient_name="J. Rivera",
        actual_pieces=20,
        actual_weight_lbs=18000,
    )
    return DeliveryRecord(**(base | over))


def codes(discs) -> set:
    return {d.code for d in discs}


# --- clean ---------------------------------------------------------------- #
def test_clean_record_has_no_discrepancies():
    discs = evaluate(make_record(), make_load())
    assert discs == []
    assert is_clean(discs) is True


def test_weight_within_tolerance_is_clean():
    # 4% under — inside the 5% default tolerance.
    discs = evaluate(make_record(actual_weight_lbs=18000 * 0.96), make_load())
    assert discs == []


# --- weight --------------------------------------------------------------- #
def test_weight_variance_over_tolerance_flags_warning():
    # 8% over expected.
    discs = evaluate(make_record(actual_weight_lbs=18000 * 1.08), make_load())
    assert codes(discs) == {DiscrepancyCode.weight_variance}
    assert discs[0].severity is Severity.warning


def test_large_weight_variance_escalates_to_critical():
    # 20% over -> critical.
    discs = evaluate(make_record(actual_weight_lbs=18000 * 1.20), make_load())
    d = next(d for d in discs if d.code is DiscrepancyCode.weight_variance)
    assert d.severity is Severity.critical


def test_weight_tolerance_is_configurable():
    cfg = DiscrepancyConfig(weight_tolerance_pct=10.0)
    # 8% over now passes the looser tolerance.
    discs = evaluate(make_record(actual_weight_lbs=18000 * 1.08), make_load(), cfg)
    assert discs == []


# --- pieces --------------------------------------------------------------- #
def test_piece_short_flags_critical():
    discs = evaluate(make_record(actual_pieces=18), make_load())
    assert codes(discs) == {DiscrepancyCode.piece_short}
    assert discs[0].severity is Severity.critical
    assert discs[0].expected == 20 and discs[0].actual == 18


def test_piece_over_flags_warning():
    discs = evaluate(make_record(actual_pieces=22), make_load())
    assert codes(discs) == {DiscrepancyCode.piece_over}
    assert discs[0].severity is Severity.warning


# --- damage --------------------------------------------------------------- #
def test_damage_flags_critical():
    discs = evaluate(make_record(damage=True, damage_notes="crushed corner"), make_load())
    assert codes(discs) == {DiscrepancyCode.damage}
    assert discs[0].severity is Severity.critical
    assert "crushed corner" in discs[0].message


# --- exception ------------------------------------------------------------ #
def test_refused_exception_flags_critical():
    discs = evaluate(make_record(exception_type="refused"), make_load())
    assert codes(discs) == {DiscrepancyCode.exception}
    assert discs[0].severity is Severity.critical


def test_short_exception_flags():
    discs = evaluate(make_record(exception_type="short"), make_load())
    assert DiscrepancyCode.exception in codes(discs)


def test_redelivery_exception_flags():
    discs = evaluate(make_record(exception_type="redelivery"), make_load())
    assert DiscrepancyCode.exception in codes(discs)


def test_non_blocking_exception_does_not_flag_exception_code():
    # ``overage`` is handled by the piece trigger, not the exception trigger.
    discs = evaluate(make_record(exception_type="overage"), make_load())
    assert DiscrepancyCode.exception not in codes(discs)


# --- recipient ------------------------------------------------------------ #
def test_missing_recipient_flags_warning():
    discs = evaluate(make_record(recipient_name=None), make_load())
    assert codes(discs) == {DiscrepancyCode.missing_recipient}
    assert discs[0].severity is Severity.warning


def test_blank_recipient_flags_warning():
    discs = evaluate(make_record(recipient_name="  "), make_load())
    assert codes(discs) == {DiscrepancyCode.missing_recipient}


# --- multiple triggers ---------------------------------------------------- #
def test_multiple_triggers_each_reported_separately():
    discs = evaluate(
        make_record(actual_pieces=15, damage=True, recipient_name=None),
        make_load(),
    )
    # Three distinct triggers — NOT collapsed into one generic flag.
    assert codes(discs) == {
        DiscrepancyCode.piece_short,
        DiscrepancyCode.damage,
        DiscrepancyCode.missing_recipient,
    }
    # And severities stay specific per trigger.
    by_code = {d.code: d.severity for d in discs}
    assert by_code[DiscrepancyCode.piece_short] is Severity.critical
    assert by_code[DiscrepancyCode.damage] is Severity.critical
    assert by_code[DiscrepancyCode.missing_recipient] is Severity.warning
