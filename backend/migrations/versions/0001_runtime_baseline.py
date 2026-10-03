"""Freeze the schema shipped in runtime foundation PR #4."""

from pathlib import Path

from alembic import op
from sqlalchemy import inspect

revision = "0001_runtime_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names(schema="public")) - {"alembic_version"}
    if tables:
        raise RuntimeError(
            "Existing unversioned schema: back up the database, then use "
            "python -m backend.migrate --adopt-runtime-baseline. "
            "Partial or ORM-created schemas are unsupported."
        )
    op.get_bind().exec_driver_sql(Path(__file__).with_suffix(".sql").read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead.")
