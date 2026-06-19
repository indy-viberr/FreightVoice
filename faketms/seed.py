from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from faketms.models import Load


def seed_database(session_factory: sessionmaker[Session]) -> None:
    demo_loads = [
        Load(
            id="FV-DEMO-001",
            pro_number="PRO-1001",
            shipper="River City Foods",
            consignee="XYZ Distribution Atlanta",
            origin_city="Memphis",
            destination_city="Atlanta",
            commodity="dry goods",
            expected_pieces=24,
            expected_weight_lbs=18400,
            scheduled_delivery=datetime(2026, 6, 19, 20, 0, tzinfo=timezone.utc),
            equipment_type="dry_van",
            notes="Clean run demo load.",
            status="pending",
        ),
        Load(
            id="FV-DEMO-002",
            pro_number="PRO-1002",
            shipper="Delta Plastics",
            consignee="Blue Ridge Packaging",
            origin_city="Nashville",
            destination_city="Charlotte",
            commodity="plastic resin",
            expected_pieces=12,
            expected_weight_lbs=9600,
            scheduled_delivery=datetime(2026, 6, 19, 20, 30, tzinfo=timezone.utc),
            equipment_type="dry_van",
            notes="Weight variance demo load.",
            status="pending",
        ),
        Load(
            id="FV-DEMO-003",
            pro_number="PRO-1003",
            shipper="Ozark Home Goods",
            consignee="Metro Retail DC",
            origin_city="Little Rock",
            destination_city="Dallas",
            commodity="home goods",
            expected_pieces=36,
            expected_weight_lbs=27000,
            scheduled_delivery=datetime(2026, 6, 19, 21, 45, tzinfo=timezone.utc),
            equipment_type="dry_van",
            notes="Damage plus detention demo load.",
            status="pending",
        ),
    ]

    with session_factory() as session:
        for load in demo_loads:
            if session.get(Load, load.id) is None:
                session.add(load)
        session.commit()

