"""Enforce retained authority, financial identity and scoped lineage."""

from pathlib import Path

from alembic import op

revision = "0002_integrity"
down_revision = "0001_runtime_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Removing integrity controls is disabled; use a forward migration.")
