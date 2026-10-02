import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.models import Agency, PaymentObligation, PaymentAttempt, BudgetEntry, utc_now

class LedgerService:
    """
    Manages agency principal limit, budget reservation, and consumption.
    Enforces Invariant I7 and NFR-03: principal is reserved, consumed, or released once.
    """

    @staticmethod
    async def reserve_budget(
        session: AsyncSession,
        agency_id: uuid.UUID,
        obligation_id: uuid.UUID,
        attempt_id: uuid.UUID,
        amount_cents: int
    ) -> bool:
        stmt = select(Agency).where(Agency.id == agency_id).with_for_update()
        res = await session.execute(stmt)
        agency = res.scalar_one_or_none()
        if not agency:
            return False

        if (agency.reserved_cents + agency.consumed_cents + amount_cents) > agency.principal_limit_cents:
            return False # Budget exceeded

        agency.reserved_cents += amount_cents

        entry = BudgetEntry(
            agency_id=agency_id,
            obligation_id=obligation_id,
            attempt_id=attempt_id,
            phase="reservation",
            kind="reserve",
            principal_cents=amount_cents,
            reserved_delta=amount_cents,
            consumed_delta=0,
            created_at=utc_now()
        )
        session.add(entry)
        await session.flush()
        return True

    @staticmethod
    async def consume_budget(
        session: AsyncSession,
        agency_id: uuid.UUID,
        obligation_id: uuid.UUID,
        attempt_id: uuid.UUID,
        amount_cents: int
    ):
        stmt = select(Agency).where(Agency.id == agency_id).with_for_update()
        res = await session.execute(stmt)
        agency = res.scalar_one_or_none()
        if not agency:
            return

        agency.reserved_cents = max(0, agency.reserved_cents - amount_cents)
        agency.consumed_cents += amount_cents

        entry = BudgetEntry(
            agency_id=agency_id,
            obligation_id=obligation_id,
            attempt_id=attempt_id,
            phase="disposition",
            kind="consume",
            principal_cents=amount_cents,
            reserved_delta=-amount_cents,
            consumed_delta=amount_cents,
            created_at=utc_now()
        )
        session.add(entry)
        await session.flush()

    @staticmethod
    async def release_budget(
        session: AsyncSession,
        agency_id: uuid.UUID,
        obligation_id: uuid.UUID,
        attempt_id: uuid.UUID,
        amount_cents: int
    ):
        stmt = select(Agency).where(Agency.id == agency_id).with_for_update()
        res = await session.execute(stmt)
        agency = res.scalar_one_or_none()
        if not agency:
            return

        agency.reserved_cents = max(0, agency.reserved_cents - amount_cents)

        entry = BudgetEntry(
            agency_id=agency_id,
            obligation_id=obligation_id,
            attempt_id=attempt_id,
            phase="disposition",
            kind="release",
            principal_cents=amount_cents,
            reserved_delta=-amount_cents,
            consumed_delta=0,
            created_at=utc_now()
        )
        session.add(entry)
        await session.flush()
