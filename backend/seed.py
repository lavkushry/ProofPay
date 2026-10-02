import asyncio
import uuid
import hashlib
from backend.app.database import AsyncSessionLocal, engine, Base
from backend.app.models import (
    Agency, User, Contractor, DemoRun, FixtureManifest, ArtifactVersion, utc_now
)
from backend.app.config import settings

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        agency_id = settings.DEFAULT_AGENCY_ID

        # 1. Agency
        agency = Agency(
            id=agency_id,
            name=settings.DEFAULT_AGENCY_NAME,
            advisory_lock_key=settings.DEFAULT_ADVISORY_LOCK_KEY,
            principal_limit_cents=1000000, # $10,000 allowance
            reserved_cents=0,
            consumed_cents=0
        )
        session.add(agency)

        # 2. Users
        owner_id = uuid.uuid4()
        owner = User(id=owner_id, agency_id=agency_id, role="owner", display_name="Sarah (Agency Owner)")

        maya_id = uuid.uuid4()
        maya_user = User(id=maya_id, agency_id=agency_id, role="contractor", display_name="Maya Lin")

        leo_id = uuid.uuid4()
        leo_user = User(id=leo_id, agency_id=agency_id, role="contractor", display_name="Leo Vance")

        judge_id = uuid.uuid4()
        judge_user = User(id=judge_id, agency_id=agency_id, role="judge", display_name="Hackathon Judge")

        session.add_all([owner, maya_user, leo_user, judge_user])

        # 3. Contractors
        contractor_maya = Contractor(
            id=uuid.uuid4(),
            agency_id=agency_id,
            user_id=maya_id,
            recipient_ref="contractor_maya",
            display_name="Maya Lin"
        )
        contractor_leo = Contractor(
            id=uuid.uuid4(),
            agency_id=agency_id,
            user_id=leo_id,
            recipient_ref="contractor_leo",
            display_name="Leo Vance"
        )
        session.add_all([contractor_maya, contractor_leo])

        # 4. Demo Run
        demo_run = DemoRun(
            id=uuid.uuid4(),
            agency_id=agency_id,
            state="active",
            created_at=utc_now()
        )
        session.add(demo_run)

        # 5. Fixture Manifest
        manifest_id = uuid.uuid4()
        manifest_data = {
            "fixture_ref": "checkout_fixture",
            "version": 1,
            "baseline_cart_cents": 4200,
            "currency": "USD",
            "supported_viewports": [320, 768, 1024],
            "controls": {"checkout_pay": "Pay now"}
        }
        manifest = FixtureManifest(
            id=manifest_id,
            agency_id=agency_id,
            fixture_ref="checkout_fixture",
            version=1,
            digest=hashlib.sha256(str(manifest_data).encode("utf-8")).hexdigest(),
            manifest=manifest_data
        )
        session.add(manifest)

        # 6. Artifact Versions
        art_broken = ArtifactVersion(
            id=uuid.uuid4(),
            agency_id=agency_id,
            manifest_id=manifest_id,
            artifact_ref="checkout_mobile_broken",
            family="responsive_css",
            digest=hashlib.sha256(b"broken_artifact_v1").hexdigest(),
            relative_path="fixtures/checkout_broken.html"
        )
        art_fixed = ArtifactVersion(
            id=uuid.uuid4(),
            agency_id=agency_id,
            manifest_id=manifest_id,
            artifact_ref="checkout_mobile_fixed",
            family="responsive_css",
            digest=hashlib.sha256(b"fixed_artifact_v1").hexdigest(),
            relative_path="fixtures/checkout_fixed.html"
        )
        session.add_all([art_broken, art_fixed])

        await session.commit()
        print("ProofPay database successfully seeded with default agency, users, and checkout fixture!")

if __name__ == "__main__":
    asyncio.run(seed())
