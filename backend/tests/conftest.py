import os
import tempfile

import pytest
from fastapi.testclient import TestClient

_test_directory = tempfile.TemporaryDirectory(prefix="proofpay-tests-")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+aiosqlite:///{_test_directory.name}/test.db"
)

from backend.app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def pytest_sessionfinish(session, exitstatus):
    _test_directory.cleanup()
