import os
import tempfile
from pathlib import Path

_TEST_DB = (Path(tempfile.gettempdir()) / "member_a_test.db").as_posix()
os.environ.setdefault("MEMBER_A_DATABASE_URL", f"sqlite:///{_TEST_DB}")

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN_PREFIX = "test-token-"


@pytest.fixture(autouse=True)
def mock_identity(monkeypatch):
    """打桩 D-API-02：任意 ``test-token-<userId>`` 令牌 → 对应用户上下文。

    阶段1鉴权闭合（2026-10-06）后 A 的浏览器端端点统一要求 Bearer JWT，
    单元测试不访问真实 D 服务（fail-closed 时直接 401）。
    """
    from src.interfaces.clients.member_d import MemberDClient

    def fake_verify_bearer(token, trace_id):
        if not token or not token.startswith(TEST_TOKEN_PREFIX):
            return None
        user_id = token[len(TEST_TOKEN_PREFIX):]
        if user_id.startswith("USER-A-"):
            permissions = ["EQUIPMENT_READ", "TELEMETRY_WRITE"]
        else:
            permissions = ["EQUIPMENT_READ"]
        return {
            "userId": user_id,
            "displayName": "测试用户",
            "roleCodes": ["EQUIPMENT_OPERATOR"],
            "permissions": permissions,
            "enabled": True,
        }

    monkeypatch.setattr(
        MemberDClient, "verify_bearer", staticmethod(fake_verify_bearer),
    )


@pytest.fixture()
def client():
    from src.domain.models import Base
    from src.infrastructure.db import SessionLocal, engine, seed_equipment

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_equipment(db)

    from src.main import app

    with TestClient(app) as test_client:
        # 默认携带操作员 Bearer（浏览器端端点鉴权闭合后的统一约定）
        test_client.headers.update({
            "Authorization": f"Bearer {TEST_TOKEN_PREFIX}USER-A-001",
        })
        yield test_client
