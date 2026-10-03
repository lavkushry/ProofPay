"""Schema changes run with migration credentials, never with the API role."""

import os

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from backend.app.database import Base
from backend.app import models  # noqa: F401 — register all mappings


def run_migrations(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Production migrations require PostgreSQL 17.")
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("Set MIGRATION_DATABASE_URL to the migration role connection.")
    engine = create_engine(make_url(url).set(drivername="postgresql+psycopg"), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
