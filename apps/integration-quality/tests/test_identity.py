import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.seed import SEED_USERS

HEADERS = {
    "X-Internal-Token": "dev-internal-token-change-me",
    "X-Trace-Id": "trace-20260917-001",
}

_CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "shared-enums.json").read_text(
        encoding="utf-8"
    )
)
_CONTRACT_PERMISSIONS = set(_CONTRACT["permissionCode"])


def test_access_context_matches_contract_example(client: TestClient):
    response = client.get("/api/v1/users/USER-C-002/access-context", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["userId"] == "USER-C-002"
    assert body["displayName"] == "维修工程师示例"
    assert body["roleCodes"] == ["MAINTENANCE_ENGINEER"]
    assert "WORK_ORDER_ACCEPT" in body["permissions"]
    assert body["organization"] == "机加车间"
    assert body["enabled"] is True


def test_seed_contains_four_roles(client: TestClient):
    expected = {
        "USER-A-001": "EQUIPMENT_OPERATOR",
        "USER-C-002": "MAINTENANCE_ENGINEER",
        "USER-C-003": "WAREHOUSE_MANAGER",
        "USER-D-001": "SYSTEM_ADMIN",
    }
    for user_id, role in expected.items():
        response = client.get(f"/api/v1/users/{user_id}/access-context", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["roleCodes"] == [role]


def test_unknown_user_returns_404(client: TestClient):
    response = client.get("/api/v1/users/USER-X-999/access-context", headers=HEADERS)
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "USER_NOT_FOUND"
    assert body["message"] == "用户不存在或已停用"
    assert body["traceId"]


def test_disabled_user_returns_404(client: TestClient, db):
    from src.domain.models import User

    db.add(
        User(
            user_id="USER-X-001",
            display_name="已停用用户",
            role_codes='["WARNING_ANALYST"]',
            permissions='["WARNING_READ"]',
            organization="测试部",
            enabled=False,
        )
    )
    db.commit()

    response = client.get("/api/v1/users/USER-X-001/access-context", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


def test_invalid_token_rejected(client: TestClient):
    response = client.get(
        "/api/v1/users/USER-C-002/access-context",
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("seed_user", SEED_USERS, ids=lambda u: u["user_id"])
def test_all_seven_roles_access_context_matches_seed(
    client: TestClient, seed_user: dict
):
    response = client.get(
        f"/api/v1/users/{seed_user['user_id']}/access-context", headers=HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["roleCodes"] == seed_user["role_codes"]
    assert set(body["permissions"]) == set(seed_user["permissions"])
    assert body["enabled"] is True
    undeclared = set(body["permissions"]) - _CONTRACT_PERMISSIONS
    assert not undeclared, f"存在契约外权限: {undeclared}"


def test_seven_roles_cover_all_contract_role_codes():
    seeded_roles = {role for u in SEED_USERS for role in u["role_codes"]}
    assert seeded_roles == set(_CONTRACT["roleCode"])
