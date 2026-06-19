from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pro_number: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    shipper: Mapped[str] = mapped_column(String(255), nullable=False)
    consignee: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_city: Mapped[str] = mapped_column(String(120), nullable=False)
    destination_city: Mapped[str] = mapped_column(String(120), nullable=False)
    commodity: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_weight_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    scheduled_delivery: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    pods: Mapped[list["Pod"]] = relationship(back_populates="load")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="load")
    discrepancies: Mapped[list["DiscrepancyRecord"]] = relationship(back_populates="load")
    callbacks: Mapped[list["Callback"]] = relationship(back_populates="load")


class Pod(Base):
    __tablename__ = "pods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    load_id: Mapped[str] = mapped_column(ForeignKey("loads.id"), nullable=False, unique=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_weight_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    damage: Mapped[bool] = mapped_column(Boolean, nullable=False)
    damage_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessorials_json: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    exception_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    load: Mapped[Load] = relationship(back_populates="pods")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    load_id: Mapped[str] = mapped_column(ForeignKey("loads.id"), nullable=False, unique=True)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    load: Mapped[Load] = relationship(back_populates="invoices")


class DiscrepancyRecord(Base):
    __tablename__ = "discrepancies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    load_id: Mapped[str] = mapped_column(ForeignKey("loads.id"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    load: Mapped[Load] = relationship(back_populates="discrepancies")


class Callback(Base):
    __tablename__ = "callbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    load_id: Mapped[str] = mapped_column(ForeignKey("loads.id"), nullable=False)
    driver_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    load: Mapped[Load] = relationship(back_populates="callbacks")
