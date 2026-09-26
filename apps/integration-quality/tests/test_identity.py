from fastapi.testclient import TestClient

HEADERS = {
    "X-Internal-Token": "dev-internal-token-change-me",
    "X-Trace-Id": "trace-20260917-001",
}


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
