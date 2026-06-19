"""
Discrepancy engine (PRD F4).

Pure functions, no I/O — this is the part of FreightVoice that decides whether a
reported delivery is clean enough to auto-invoice or whether a human needs to
look at it. Every trigger produces its own ``Discrepancy`` with its own
severity; we deliberately do NOT collapse everything into one generic "needs
review" flag, because the carrier's exception desk routes detention differently
from damage differently from a short count.

A clean record returns ``[]`` and the caller proceeds to invoice.

Tunable thresholds live in ``DiscrepancyConfig`` so the 5% weight tolerance is
configurable rather than a magic number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .schemas import DeliveryRecord, ExceptionType, LoadContext


class Severity(str, Enum):
    """How urgently a human needs to look. Specific per trigger, never generic."""

    info = "info"
    warning = "warning"
    critical = "critical"


class DiscrepancyCode(str, Enum):
    """Stable machine codes so the dashboard/queue can route and badge each kind."""

    weight_variance = "weight_variance"
    piece_short = "piece_short"
    piece_over = "piece_over"
    damage = "damage"
    exception = "exception"
    missing_recipient = "missing_recipient"


@dataclass(frozen=True)
class Discrepancy:
    """One thing wrong with a delivery record, with enough context to act."""

    code: DiscrepancyCode
    severity: Severity
    message: str
    expected: object | None = None
    actual: object | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True)
class DiscrepancyConfig:
    """Tunable thresholds. Defaults match the PRD."""

    weight_tolerance_pct: float = 5.0
    # Exceptions that block a clean invoice on their own. ``overage`` /
    # ``damaged`` are covered by the dedicated piece/damage triggers, so the
    # exception trigger focuses on the disposition exceptions.
    blocking_exceptions: frozenset[ExceptionType] = frozenset(
        {ExceptionType.refused, ExceptionType.short, ExceptionType.redelivery}
    )


DEFAULT_CONFIG = DiscrepancyConfig()


def evaluate(
    record: DeliveryRecord,
    load: LoadContext,
    config: DiscrepancyConfig = DEFAULT_CONFIG,
) -> list[Discrepancy]:
    """Return every discrepancy between ``record`` and ``load``.

    Order is stable (weight, pieces, damage, exception, recipient) so logs and
    tests read predictably. An empty list means "clean — safe to invoice".
    """

    out: list[Discrepancy] = []

    _check_weight(record, load, config, out)
    _check_pieces(record, load, out)
    _check_damage(record, out)
    _check_exception(record, config, out)
    _check_recipient(record, out)

    return out


def is_clean(discrepancies: list[Discrepancy]) -> bool:
    return len(discrepancies) == 0


# --------------------------------------------------------------------------- #
# Individual triggers — each owns its severity.
# --------------------------------------------------------------------------- #
def _check_weight(
    record: DeliveryRecord,
    load: LoadContext,
    config: DiscrepancyConfig,
    out: list[Discrepancy],
) -> None:
    expected = load.expected_weight_lbs
    if expected <= 0:
        # No baseline to compare against; can't assert a variance.
        return
    variance_pct = abs(record.actual_weight_lbs - expected) / expected * 100.0
    if variance_pct > config.weight_tolerance_pct:
        # Weight off is a billing/safety signal but rarely a refuse-the-load
        # event -> warning, escalating to critical if it's way out (>15%).
        severity = Severity.critical if variance_pct > 15.0 else Severity.warning
        out.append(
            Discrepancy(
                code=DiscrepancyCode.weight_variance,
                severity=severity,
                message=(
                    f"Actual weight {record.actual_weight_lbs:.0f} lbs is "
                    f"{variance_pct:.1f}% off expected {expected:.0f} lbs "
                    f"(tolerance {config.weight_tolerance_pct:.0f}%)."
                ),
                expected=expected,
                actual=record.actual_weight_lbs,
            )
        )


def _check_pieces(
    record: DeliveryRecord, load: LoadContext, out: list[Discrepancy]
) -> None:
    if record.actual_pieces < load.expected_pieces:
        # A short count means freight is missing — high stakes, blocks invoice.
        out.append(
            Discrepancy(
                code=DiscrepancyCode.piece_short,
                severity=Severity.critical,
                message=(
                    f"Short {load.expected_pieces - record.actual_pieces} piece(s): "
                    f"delivered {record.actual_pieces} of {load.expected_pieces}."
                ),
                expected=load.expected_pieces,
                actual=record.actual_pieces,
            )
        )
    elif record.actual_pieces > load.expected_pieces:
        # Overage is a discrepancy but lower stakes than missing freight.
        out.append(
            Discrepancy(
                code=DiscrepancyCode.piece_over,
                severity=Severity.warning,
                message=(
                    f"Overage of {record.actual_pieces - load.expected_pieces} piece(s): "
                    f"delivered {record.actual_pieces} of {load.expected_pieces}."
                ),
                expected=load.expected_pieces,
                actual=record.actual_pieces,
            )
        )


def _check_damage(record: DeliveryRecord, out: list[Discrepancy]) -> None:
    if record.damage:
        out.append(
            Discrepancy(
                code=DiscrepancyCode.damage,
                severity=Severity.critical,
                message=(
                    "Damage reported"
                    + (f": {record.damage_notes}" if record.damage_notes else ".")
                ),
                expected=False,
                actual=True,
            )
        )


def _check_exception(
    record: DeliveryRecord, config: DiscrepancyConfig, out: list[Discrepancy]
) -> None:
    if record.exception_type in config.blocking_exceptions:
        out.append(
            Discrepancy(
                code=DiscrepancyCode.exception,
                severity=Severity.critical,
                message=f"Delivery exception: {record.exception_type.value}.",
                expected=None,
                actual=record.exception_type.value,
            )
        )


def _check_recipient(record: DeliveryRecord, out: list[Discrepancy]) -> None:
    # ``DeliveryRecord`` already normalizes blank -> None.
    if record.recipient_name is None:
        out.append(
            Discrepancy(
                code=DiscrepancyCode.missing_recipient,
                severity=Severity.warning,
                message="No recipient name captured — POD lacks a signature of record.",
                expected="<name>",
                actual=None,
            )
        )
