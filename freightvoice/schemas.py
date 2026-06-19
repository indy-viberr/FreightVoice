from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EquipmentType(str, Enum):
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"
    STEP_DECK = "step_deck"
    TANKER = "tanker"
    LTL = "ltl"
    OTHER = "other"


class AccessorialType(str, Enum):
    DETENTION = "detention"
    LIFTGATE = "liftgate"
    LUMPER = "lumper"
    RESIDENTIAL = "residential"
    INSIDE_DELIVERY = "inside_delivery"
    LAYOVER = "layover"
    TONU = "tonu"
    REDELIVERY = "redelivery"


class ExceptionType(str, Enum):
    REFUSED = "refused"
    SHORT = "short"
    DAMAGE = "damage"
    REDELIVERY = "redelivery"
    OVERAGE = "overage"


class DiscrepancySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class LoadContext(StrictBaseModel):
    """Returned by get_load_context webhook; spoken back by agent to confirm."""

    load_id: str
    pro_number: str | None = None
    shipper: str
    consignee: str
    origin_city: str
    destination_city: str
    commodity: str
    expected_pieces: int
    expected_weight_lbs: float
    scheduled_delivery: datetime
    equipment_type: EquipmentType
    notes: str | None = None


class AccessorialEvent(StrictBaseModel):
    """One accessorial service performed during the delivery."""

    type: AccessorialType
    duration_minutes: int | None = None
    amount_usd: float | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_required_fields(self) -> "AccessorialEvent":
        if self.type in {AccessorialType.DETENTION, AccessorialType.LAYOVER} and self.duration_minutes is None:
            raise ValueError(f"{self.type.value} requires duration_minutes")
        if self.type == AccessorialType.LUMPER and self.amount_usd is None:
            raise ValueError("lumper requires amount_usd")
        return self


class DeliveryRecord(StrictBaseModel):
    """Full post-delivery capture; pushed by push_delivery_record webhook."""

    load_id: str
    delivered_at: datetime
    recipient_name: str
    actual_pieces: int
    actual_weight_lbs: float
    damage: bool
    damage_notes: str | None = None
    accessorials: list[AccessorialEvent] = Field(default_factory=list)
    exception_type: ExceptionType | None = None
    transcript_excerpt: str | None = None

    @model_validator(mode="after")
    def damage_notes_required(self) -> "DeliveryRecord":
        if self.damage and not self.damage_notes:
            raise ValueError("damage_notes required when damage is True")
        return self


class Discrepancy(StrictBaseModel):
    """One specific problem found by the validation engine."""

    trigger: str
    severity: DiscrepancySeverity
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(StrictBaseModel):
    """Output of the discrepancy engine."""

    load_id: str
    is_clean: bool
    discrepancies: list[Discrepancy]


class VapiToolCallFunction(StrictBaseModel):
    name: str
    arguments: dict[str, Any]


class VapiToolCall(StrictBaseModel):
    id: str
    type: Literal["function"]
    function: VapiToolCallFunction


class VapiToolCallRequest(StrictBaseModel):
    """Inbound webhook body from Vapi server-tool calls.

    The current documented shape wraps tool calls in message.toolCalls:
    https://docs.vapi.ai/server-url/events#tool-calls
    """

    message: dict[str, Any]

    def get_tool_calls(self) -> list[VapiToolCall]:
        return [VapiToolCall(**tool_call) for tool_call in self.message.get("toolCalls", [])]


class VapiToolResult(StrictBaseModel):
    toolCallId: str
    result: str


class VapiToolCallResponse(StrictBaseModel):
    results: list[VapiToolResult]

