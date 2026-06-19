"""
FreightVoice canonical schemas.

These pydantic models are the contract between the voice agent (Vapi) and the
carrier's TMS. They are deliberately strict: an LLM produces tool-call arguments
and we will not let a hallucinated field or an invented accessorial type flow
through to a real invoice. Validation errors are surfaced back to the agent so
it can re-ask the driver rather than guessing.

Three models matter:

* ``LoadContext``    — what the TMS knows about a load *before* the call. The
                       agent confirms these facts with the driver; it never
                       dictates them.
* ``AccessorialEvent`` — a billable extra (detention, liftgate, ...). The
                       ``type`` is a closed enum; unknown types are rejected.
* ``DeliveryRecord`` — what the driver reported *after* the call. This is the
                       payload that the discrepancy engine inspects and, if
                       clean, that triggers invoicing.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    """Base for every model: reject unknown fields, validate on assignment.

    ``extra="forbid"`` is what makes "reject unknown accessorial types" and
    "reject typo'd fields" work — pydantic raises instead of silently dropping.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EquipmentType(str, Enum):
    dry_van = "dry_van"
    reefer = "reefer"
    flatbed = "flatbed"
    step_deck = "step_deck"
    box_truck = "box_truck"
    power_only = "power_only"


class AccessorialType(str, Enum):
    """Closed set of billable extras. Anything outside this set is rejected.

    Names mirror common freight-billing line items so the readback the agent
    speaks matches what the carrier's AP team expects to see.
    """

    detention = "detention"
    liftgate = "liftgate"
    lumper = "lumper"
    residential = "residential"
    inside_delivery = "inside_delivery"
    layover = "layover"
    tonu = "tonu"  # truck-ordered-not-used


class ExceptionType(str, Enum):
    """Delivery exceptions that, by themselves, should block a clean invoice."""

    refused = "refused"
    short = "short"
    redelivery = "redelivery"
    damaged = "damaged"
    overage = "overage"


def normalize_load_id(value: str) -> str:
    """Canonicalize spoken load/PRO identifiers without changing punctuation."""
    return value.strip().upper()


# --------------------------------------------------------------------------- #
# Load context (TMS -> agent)
# --------------------------------------------------------------------------- #
class LoadContext(_Strict):
    """The pre-delivery facts about a load, pulled from the TMS.

    Returned by ``get_load_context`` so the agent can confirm-not-dictate:
    it reads the consignee/commodity/expected counts to the driver and asks
    yes/no questions rather than open-ended ones.
    """

    load_id: str = Field(..., min_length=1, description="Carrier load id / PRO number")
    shipper: str = Field(..., min_length=1)
    consignee: str = Field(..., min_length=1)
    commodity: str = Field(..., min_length=1)
    expected_pieces: int = Field(..., ge=0)
    expected_weight_lbs: float = Field(..., ge=0)
    scheduled_delivery: datetime
    equipment_type: EquipmentType


# --------------------------------------------------------------------------- #
# Accessorial (agent -> TMS, nested in DeliveryRecord)
# --------------------------------------------------------------------------- #
class AccessorialEvent(_Strict):
    """A single billable extra captured during the call.

    ``duration_minutes`` and ``amount_usd`` are both optional because the driver
    often knows one but not the other (e.g. "I waited two hours" with no dollar
    figure). The carrier's rate engine fills the rest; we only capture what the
    driver actually said.
    """

    type: AccessorialType
    duration_minutes: int | None = Field(default=None, ge=0)
    amount_usd: float | None = Field(default=None, ge=0)
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Delivery record (agent -> TMS)
# --------------------------------------------------------------------------- #
class DeliveryRecord(_Strict):
    """The completed proof-of-delivery as reported by the driver on the call.

    This is the discrepancy engine's input. ``actual_pieces`` /
    ``actual_weight_lbs`` are compared against the load's expected values;
    ``damage`` / ``exception_type`` / ``recipient_name`` each independently
    decide whether the record can auto-invoice.
    """

    load_id: str = Field(..., min_length=1)
    delivered_at: datetime
    recipient_name: str | None = Field(
        default=None,
        description="Who signed for it. Absent => no clean POD => flag.",
    )
    actual_pieces: int = Field(..., ge=0)
    actual_weight_lbs: float = Field(..., ge=0)
    damage: bool = False
    damage_notes: str | None = None
    accessorials: list[AccessorialEvent] = Field(default_factory=list)
    exception_type: ExceptionType | None = None
    transcript_excerpt: str | None = Field(
        default=None,
        description="Short verbatim snippet for the discrepancy queue / audit.",
    )

    @field_validator("load_id", mode="before")
    @classmethod
    def _normalize_load_id(cls, v):
        if isinstance(v, str):
            return normalize_load_id(v)
        return v

    @field_validator("exception_type", mode="before")
    @classmethod
    def _vapi_none_exception_is_none(cls, v):
        """Normalize Vapi's explicit no-exception sentinel to an absent value."""
        if isinstance(v, str) and v.strip().lower() == "none":
            return None
        return v

    @field_validator("recipient_name")
    @classmethod
    def _blank_name_is_none(cls, v: str | None) -> str | None:
        """Treat a whitespace-only recipient as missing.

        The agent may pass an empty string when the driver mumbled a name it
        couldn't parse. Normalize to ``None`` so the discrepancy engine's
        "missing recipient" trigger fires consistently instead of passing a
        blank string through to the POD.
        """
        if v is None:
            return None
        v = v.strip()
        return v or None
