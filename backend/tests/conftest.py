import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

_test_directory = tempfile.TemporaryDirectory(prefix="proofpay-tests-")
# Unit doubles never inherit an operator's application/database connection.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_directory.name}/test.db"

from backend.app.main import app
from backend.app.database import Base


@pytest.fixture(scope="session", autouse=True)
def unit_test_schema():
    # SQLite is only a fast unit-test double; PostgreSQL acceptance uses Alembic.
    unit_engine = create_engine(os.environ["DATABASE_URL"].replace("+aiosqlite", ""))
    Base.metadata.create_all(unit_engine)
    unit_engine.dispose()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def pytest_sessionfinish(session, exitstatus):
    _test_directory.cleanup()
