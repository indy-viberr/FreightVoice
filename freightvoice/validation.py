from __future__ import annotations

from freightvoice.schemas import (
    DeliveryRecord,
    Discrepancy,
    DiscrepancySeverity,
    ExceptionType,
    LoadContext,
    ValidationResult,
)


SEVERITY_RANK: dict[DiscrepancySeverity, int] = {
    DiscrepancySeverity.INFO: 10,
    DiscrepancySeverity.WARNING: 20,
    DiscrepancySeverity.CRITICAL: 30,
}


def run_validation(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float = 5.0,
    piece_variance_allow: int = 0,
    auto_invoice_below_severity: str = "warning",
) -> ValidationResult:
    """Run all discrepancy checks without I/O or side effects."""

    checks = [
        _check_weight_variance,
        _check_piece_short,
        _check_piece_overage,
        _check_damage_reported,
        _check_exception_refused,
        _check_exception_short_shipment,
        _check_exception_redelivery,
        _check_missing_recipient,
    ]
    discrepancies: list[Discrepancy] = []
    for check in checks:
        discrepancy = check(record, context, weight_variance_pct, piece_variance_allow)
        if discrepancy is not None:
            discrepancies.append(discrepancy)

    threshold = DiscrepancySeverity(auto_invoice_below_severity)
    is_clean = all(SEVERITY_RANK[item.severity] < SEVERITY_RANK[threshold] for item in discrepancies)
    return ValidationResult(load_id=record.load_id, is_clean=is_clean, discrepancies=discrepancies)


def _check_weight_variance(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del piece_variance_allow
    if context.expected_weight_lbs == 0:
        if record.actual_weight_lbs == 0:
            return None
        variance_pct = 100.0
    else:
        variance_pct = abs(record.actual_weight_lbs - context.expected_weight_lbs) / context.expected_weight_lbs * 100
    if variance_pct <= weight_variance_pct:
        return None
    severity = DiscrepancySeverity.CRITICAL if variance_pct > 15 else DiscrepancySeverity.WARNING
    return Discrepancy(
        trigger="weight_variance",
        severity=severity,
        message=(
            f"Actual weight {record.actual_weight_lbs:,.0f} lbs differs from expected "
            f"{context.expected_weight_lbs:,.0f} lbs by {variance_pct:.1f}%."
        ),
        detail={
            "expected_lbs": context.expected_weight_lbs,
            "actual_lbs": record.actual_weight_lbs,
            "variance_pct": round(variance_pct, 1),
        },
    )


def _check_piece_short(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del weight_variance_pct
    if record.actual_pieces >= context.expected_pieces - piece_variance_allow:
        return None
    short_by = context.expected_pieces - record.actual_pieces
    return Discrepancy(
        trigger="piece_short",
        severity=DiscrepancySeverity.WARNING,
        message=f"Piece count is short by {short_by}.",
        detail={"expected": context.expected_pieces, "actual": record.actual_pieces, "short_by": short_by},
    )


def _check_piece_overage(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del weight_variance_pct, piece_variance_allow
    if record.actual_pieces <= context.expected_pieces:
        return None
    over_by = record.actual_pieces - context.expected_pieces
    return Discrepancy(
        trigger="piece_overage",
        severity=DiscrepancySeverity.INFO,
        message=f"Piece count is over by {over_by}.",
        detail={"expected": context.expected_pieces, "actual": record.actual_pieces, "over_by": over_by},
    )


def _check_damage_reported(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del context, weight_variance_pct, piece_variance_allow
    if not record.damage:
        return None
    return Discrepancy(
        trigger="damage_reported",
        severity=DiscrepancySeverity.CRITICAL,
        message="Damage was reported on delivery.",
        detail={"damage_notes": record.damage_notes},
    )


def _check_exception_refused(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del context, weight_variance_pct, piece_variance_allow
    if record.exception_type != ExceptionType.REFUSED:
        return None
    return Discrepancy(
        trigger="exception_refused",
        severity=DiscrepancySeverity.CRITICAL,
        message="Delivery was refused.",
        detail={"exception_type": record.exception_type.value},
    )


def _check_exception_short_shipment(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del context, weight_variance_pct, piece_variance_allow
    if record.exception_type != ExceptionType.SHORT:
        return None
    return Discrepancy(
        trigger="exception_short_shipment",
        severity=DiscrepancySeverity.WARNING,
        message="Driver reported a short shipment exception.",
        detail={"exception_type": record.exception_type.value},
    )


def _check_exception_redelivery(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del context, weight_variance_pct, piece_variance_allow
    if record.exception_type != ExceptionType.REDELIVERY:
        return None
    return Discrepancy(
        trigger="exception_redelivery",
        severity=DiscrepancySeverity.WARNING,
        message="Driver reported a redelivery exception.",
        detail={"exception_type": record.exception_type.value},
    )


def _check_missing_recipient(
    record: DeliveryRecord,
    context: LoadContext,
    weight_variance_pct: float,
    piece_variance_allow: int,
) -> Discrepancy | None:
    del context, weight_variance_pct, piece_variance_allow
    if record.recipient_name.strip():
        return None
    return Discrepancy(
        trigger="missing_recipient",
        severity=DiscrepancySeverity.CRITICAL,
        message="Recipient name is missing.",
        detail={},
    )

