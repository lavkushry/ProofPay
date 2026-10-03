"""Separate runtime authority from the schema owner."""

from pathlib import Path

from alembic import op

revision = "0003_runtime_grants"
down_revision = "0002_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Do not downgrade runtime privilege boundaries.")
