"""Preserve verification inputs and immutable completion/bundle identities."""

from pathlib import Path

from alembic import op

revision = "0005_verification"
down_revision = "0004_command_leases"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Do not discard verification provenance or completion identities.")
