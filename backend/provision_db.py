"""Administrative role provisioning, isolated from runtime containers."""

import os

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def provision_roles(url, passwords):
    parsed = make_url(url)
    with psycopg.connect(parsed.set(drivername="postgresql").render_as_string(hide_password=False)) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(847291038470)")
        for role, password in passwords.items():
            if role not in ("proofpay_migrator", "proofpay_api", "proofpay_executor"):
                raise ValueError("Unsupported role")
            if not password:
                raise ValueError("All role passwords must be explicitly configured")
            if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            connection.execute(sql.SQL(
                "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password)))
        memberships = connection.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
            "WHERE r.rolname IN ('proofpay_api','proofpay_executor') LIMIT 1"
        ).fetchone()
        if memberships:
            raise ValueError("Runtime roles must not inherit other roles; review existing memberships")
        # Fresh Compose database uses the migration role as its object owner.
        connection.execute(sql.SQL("ALTER DATABASE {} OWNER TO proofpay_migrator").format(sql.Identifier(parsed.database)))
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("ALTER SCHEMA public OWNER TO proofpay_migrator")
        connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(parsed.database)))
        connection.execute(sql.SQL(
            "GRANT CONNECT ON DATABASE {} TO proofpay_migrator, proofpay_api, proofpay_executor"
        ).format(sql.Identifier(parsed.database)))


def main():
    try:
        provision_roles(os.environ["ADMIN_DATABASE_URL"], {
            "proofpay_migrator": os.environ["PROOFPAY_MIGRATOR_PASSWORD"],
            "proofpay_api": os.environ["PROOFPAY_API_PASSWORD"],
            "proofpay_executor": os.environ["PROOFPAY_EXECUTOR_PASSWORD"],
        })
    except Exception as error:
        raise SystemExit(f"Role provisioning failed ({type(error).__name__}); no secrets logged.") from None
    print("Provisioned separate migration, API and executor roles.")


if __name__ == "__main__":
    main()
