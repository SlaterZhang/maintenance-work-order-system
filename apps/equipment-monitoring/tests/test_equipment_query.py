from fastapi.testclient import TestClient


def test_get_equipment_returns_v2_equipment_fields(client: TestClient):
    response = client.get(
        "/api/v1/equipment/EQ-000001", headers={"X-Trace-Id": "trace-20260917-001"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["equipmentId"] == "EQ-000001"
    assert body["name"] == "一号数控机床"
    assert body["equipmentType"] == "CNC"
    assert body["productionLineId"] == "LINE-01"
    assert body["location"] == "一车间 A 区"
    assert body["manufacturer"] == "示例机床厂"
    assert body["model"] == "CNC-X1000"
    assert body["responsibleDepartment"] == "机加车间"
    assert body["currentStatus"] == "RUNNING"
    assert body["enabled"] is True
    assert body["version"] == 0
    assert body["createdAt"].endswith("Z")
    assert body["updatedAt"].endswith("Z")


def test_seed_contains_three_equipment(client: TestClient):
    for equipment_id in ("EQ-000001", "EQ-000002", "EQ-000003"):
        response = client.get(f"/api/v1/equipment/{equipment_id}")
        assert response.status_code == 200
        assert response.json()["equipmentId"] == equipment_id


def test_get_equipment_not_found_returns_error_response(client: TestClient):
    response = client.get(
        "/api/v1/equipment/EQ-999999", headers={"X-Trace-Id": "trace-20260917-001"}
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "EQUIPMENT_NOT_FOUND"
    assert body["message"] == "设备不存在"
    assert body["traceId"]
