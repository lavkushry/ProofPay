"""Idempotent base identities; verified demo cases are seeded in a later milestone."""

import asyncio
import uuid

from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, engine
from backend.app.models import Agency, Contractor, DemoRun, User
from backend.app.services.catalog import seed_catalog
from fixture_contract.registry import load_contract


async def seed():
    contract = load_contract()  # Verify packaged bytes before opening a database transaction.
    async with AsyncSessionLocal() as session:
        if engine.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": settings.DEFAULT_ADVISORY_LOCK_KEY},
            )
        agency_id = settings.DEFAULT_AGENCY_ID
        if await session.get(Agency, agency_id):
            await seed_catalog(session, agency_id, contract)
            await session.commit()
            print("Base identities/history preserved; trusted fixture catalog verified.")
            return

        agency = Agency(
            id=agency_id,
            name=settings.DEFAULT_AGENCY_NAME,
            advisory_lock_key=settings.DEFAULT_ADVISORY_LOCK_KEY,
            principal_limit_cents=settings.WORKSPACE_PRINCIPAL_LIMIT_CENTS,
            reserved_cents=0,
            consumed_cents=0,
        )
        session.add(agency)
        await session.flush()

        personas = (
            ("owner", "Sarah (Agency Owner)"),
            ("contractor", "Maya Lin"),
            ("contractor", "Leo Vance"),
            ("judge", "Hackathon Judge"),
        )
        users = [
            User(id=uuid.uuid4(), agency_id=agency_id, role=role, display_name=name)
            for role, name in personas
        ]
        session.add_all(users)
        await session.flush()
        for recipient, user in zip(("contractor_maya", "contractor_leo"), users[1:3]):
            session.add(Contractor(
                id=uuid.uuid4(), agency_id=agency_id, user_id=user.id,
                recipient_ref=recipient, display_name=user.display_name,
            ))
        await session.flush()

        run = DemoRun(id=uuid.uuid4(), agency_id=agency_id, state="active")
        session.add(run)
        await session.flush()
        agency.current_demo_run_id = run.id
        await seed_catalog(session, agency_id, contract)
        await session.commit()
        print("Seeded identities and trusted fixture catalog; model/verified cases/receiver bindings remain pending.")


if __name__ == "__main__":
    asyncio.run(seed())
