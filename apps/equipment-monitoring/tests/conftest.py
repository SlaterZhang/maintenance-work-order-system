from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.config import Settings  # noqa: E402
from src.interfaces.http import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path: Path):
    return create_app(
        Settings(
            database_path=tmp_path / "equipment-test.db",
            seed_on_start=True,
            internal_api_token="test-internal-token",
        )
    )


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def write_headers() -> dict[str, str]:
    return {
        "Idempotency-Key": "11111111-1111-4111-8111-111111111111",
        "X-Trace-Id": "trace-a-test-001",
    }


@pytest.fixture
def internal_headers() -> dict[str, str]:
    return {
        "Idempotency-Key": "22222222-2222-4222-8222-222222222222",
        "X-Trace-Id": "trace-20260917-001",
        "X-Internal-Token": "test-internal-token",
    }
