"""Preserve job inputs and accepted stages; enforce lease projection consistency."""

from pathlib import Path
from alembic import op

revision = "0004_command_leases"
down_revision = "0003_runtime_grants"
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Use a reviewed forward migration for retained command/lease history.")
