"""Run PostgreSQL migrations, with explicit, checked adoption of the PR #4 schema."""

import argparse
import os
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

MIGRATIONS = Path(__file__).parent / "migrations"
HEAD_REVISION = "0003_runtime_grants"


def alembic_config(connection=None):
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def schema_signature(connection, schema):
    """Compare structure, not object names or row data, for legacy adoption."""
    inspector = inspect(connection)
    signature = {}
    for table in inspector.get_table_names(schema=schema):
        if table == "alembic_version":
            continue
        columns = tuple(
            (c["name"], str(c["type"]), c["nullable"], c.get("default"), c.get("identity"))
            for c in inspector.get_columns(table, schema=schema)
        )
        foreign_keys = sorted(
            (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]),
             "local" if f["referred_schema"] in (None, schema) else f["referred_schema"],
             f.get("options", {}))
            for f in inspector.get_foreign_keys(table, schema=schema)
        )
        uniques = sorted(tuple(u["column_names"]) for u in inspector.get_unique_constraints(table, schema=schema))
        checks = sorted(c["sqltext"] for c in inspector.get_check_constraints(table, schema=schema))
        indexes = sorted(
            (i["unique"], tuple(i["column_names"]), i.get("dialect_options", {}))
            for i in inspector.get_indexes(table, schema=schema)
        )
        triggers = connection.execute(text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid=to_regclass(:table) AND NOT tgisinternal ORDER BY tgname"
        ), {"table": f"{schema}.{table}"}).scalars().all()
        signature[table] = (columns, foreign_keys, uniques, checks, indexes,
                            inspector.get_pk_constraint(table, schema=schema)["constrained_columns"], triggers)
    return signature


def adopt_runtime_baseline(connection):
    """Accept only the complete, structurally identical initialization schema."""
    if connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar():
        raise RuntimeError("Database is already versioned; use a normal upgrade.")
    reference_schema = "baseline_check_" + uuid.uuid4().hex
    actual = schema_signature(connection, "public")
    connection.exec_driver_sql(f'CREATE SCHEMA "{reference_schema}"')
    connection.exec_driver_sql(f'SET LOCAL search_path TO "{reference_schema}", public')
    baseline = (MIGRATIONS / "versions/0001_runtime_baseline.sql").read_text()
    # UUIDs are application-generated; the old unused extension is not schema authority.
    baseline = baseline.replace('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";', '')
    connection.exec_driver_sql(baseline)
    expected = schema_signature(connection, reference_schema)
    connection.exec_driver_sql('SET LOCAL search_path TO public')
    connection.exec_driver_sql(f'DROP SCHEMA "{reference_schema}" CASCADE')
    if actual != expected:
        differences = sorted(t for t in actual.keys() | expected.keys() if actual.get(t) != expected.get(t))
        raise RuntimeError("Unsupported legacy schema; mismatched tables: " + ", ".join(differences))
    # Only the fully checked baseline is transferred; no cluster-wide REASSIGN OWNED.
    for table in sorted(actual):
        connection.exec_driver_sql(f'ALTER TABLE public."{table}" OWNER TO proofpay_migrator')
    connection.exec_driver_sql("SET LOCAL ROLE proofpay_migrator")
    command.stamp(alembic_config(connection), "0001_runtime_baseline")


def upgrade_database(url, adopt=False):
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Production migrations require PostgreSQL 17.")
    engine = create_engine(parsed.set(drivername="postgresql+psycopg"), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            # Serialize migration/adoption; use a separate key from the agency workflow lock.
            connection.execute(text("SELECT pg_advisory_xact_lock(847291038471)"))
            if adopt:
                adopt_runtime_baseline(connection)
            command.upgrade(alembic_config(connection), "head")
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adopt-runtime-baseline", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        parser.error("Set MIGRATION_DATABASE_URL; API credentials cannot migrate.")
    try:
        upgrade_database(url, adopt=args.adopt_runtime_baseline)
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        # Never log SQL parameters, connection strings or business bytes on failure.
        raise SystemExit(f"Migration failed ({type(error).__name__}). Consult the migration guide and database logs.") from None
    print(f"Database schema is at {HEAD_REVISION}.")


if __name__ == "__main__":
    main()
