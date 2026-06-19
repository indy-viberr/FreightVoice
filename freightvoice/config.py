from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, field_validator


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    FREIGHTVOICE_PORT: int = 5000
    FAKETMS_PORT: int = 5001
    FAKETMS_URL: str = "http://localhost:5001"
    FREIGHTVOICE_TMS: str = "fake"
    FREIGHTVOICE_FACTORING: str = "fake"
    VAPI_AUTH_TOKEN: str = ""
    NEBIUS_API_KEY: str = ""
    WEIGHT_VARIANCE_PCT: float = 5.0
    PIECE_VARIANCE_ALLOW: int = 0
    WEBHOOK_SECRET: str = ""
    AUTO_INVOICE_BELOW_SEVERITY: str = "warning"
    FAKETMS_DATABASE_URL: str = "sqlite:///faketms.sqlite3"

    @field_validator("FREIGHTVOICE_TMS")
    @classmethod
    def validate_tms(cls, value: str) -> str:
        if value not in {"fake", "samsara", "motive"}:
            raise ValueError("FREIGHTVOICE_TMS must be fake, samsara, or motive")
        return value

    @field_validator("FREIGHTVOICE_FACTORING")
    @classmethod
    def validate_factoring(cls, value: str) -> str:
        if value not in {"fake", "rts"}:
            raise ValueError("FREIGHTVOICE_FACTORING must be fake or rts")
        return value

    @field_validator("AUTO_INVOICE_BELOW_SEVERITY")
    @classmethod
    def validate_auto_invoice_severity(cls, value: str) -> str:
        if value not in {"info", "warning", "critical"}:
            raise ValueError("AUTO_INVOICE_BELOW_SEVERITY must be info, warning, or critical")
        return value

    @classmethod
    def from_env(cls, override: dict[str, object] | None = None) -> "Config":
        load_dotenv()
        values: dict[str, object] = {}
        for name, field_info in cls.model_fields.items():
            raw = os.getenv(name)
            if raw is None:
                continue
            annotation = field_info.annotation
            if annotation is int:
                values[name] = int(raw)
            elif annotation is float:
                values[name] = float(raw)
            else:
                values[name] = raw
        if override:
            values.update(override)
        return cls(**values)
