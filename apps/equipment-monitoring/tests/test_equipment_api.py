from __future__ import annotations


def test_list_and_get_seeded_equipment(client) -> None:
    response = client.get(
        "/api/v1/equipment",
        params={"productionLineId": "LINE-01", "status": "RUNNING"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["equipmentId"] == "EQ-000001"

    detail = client.get("/api/v1/equipment/EQ-000003")
    assert detail.status_code == 200
    assert detail.json()["currentStatus"] == "STOPPED"
    assert detail.json()["manufacturer"] == "示例泵业"


def test_get_missing_equipment_returns_contract_error(client) -> None:
    response = client.get(
        "/api/v1/equipment/EQ-999999",
        headers={"X-Trace-Id": "trace-not-found"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "EQUIPMENT_NOT_FOUND",
        "message": "设备不存在",
        "traceId": "trace-not-found",
        "timestamp": response.json()["timestamp"],
        "details": [],
    }
    assert response.headers["X-Trace-Id"] == response.json()["traceId"]


def test_generated_trace_id_is_consistent_between_header_and_error_body(client) -> None:
    response = client.get("/api/v1/equipment/EQ-999999")

    assert response.status_code == 404
    assert response.headers["X-Trace-Id"] == response.json()["traceId"]


def test_create_is_idempotent_and_equipment_id_is_stable(client, write_headers) -> None:
    body = {
        "name": "三号电机",
        "equipmentType": "MOTOR",
        "productionLineId": "LINE-02",
        "location": "二车间 C 区",
        "manufacturer": None,
        "model": "M-300",
        "responsibleDepartment": "动力设备部",
    }

    first = client.post("/api/v1/equipment", json=body, headers=write_headers)
    second = client.post("/api/v1/equipment", json=body, headers=write_headers)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["equipmentId"] == "EQ-000004"
    assert first.json()["currentStatus"] == "STOPPED"
    assert first.json()["version"] == 0
    assert client.get("/api/v1/equipment").json()["total"] == 4


def test_reusing_idempotency_key_with_different_body_is_conflict(
    client, write_headers
) -> None:
    body = {
        "name": "新设备",
        "equipmentType": "CNC",
        "productionLineId": "LINE-01",
        "location": "一车间",
    }
    assert client.post("/api/v1/equipment", json=body, headers=write_headers).status_code == 201
    body["name"] = "另一台设备"

    response = client.post("/api/v1/equipment", json=body, headers=write_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_update_uses_optimistic_lock(client) -> None:
    headers = {
        "Idempotency-Key": "33333333-3333-4333-8333-333333333333",
        "X-Trace-Id": "trace-update-001",
    }
    response = client.patch(
        "/api/v1/equipment/EQ-000001",
        json={"expectedVersion": 0, "location": "一车间 C 区", "enabled": False},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert response.json()["location"] == "一车间 C 区"
    assert response.json()["enabled"] is False

    conflict = client.patch(
        "/api/v1/equipment/EQ-000001",
        json={"expectedVersion": 0, "name": "过期修改"},
        headers={
            "Idempotency-Key": "44444444-4444-4444-8444-444444444444",
            "X-Trace-Id": "trace-update-002",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "VERSION_CONFLICT"
    assert conflict.json()["details"][0]["field"] == "expectedVersion"


def test_update_requires_a_changed_field(client) -> None:
    response = client.patch(
        "/api/v1/equipment/EQ-000001",
        json={"expectedVersion": 0},
        headers={
            "Idempotency-Key": "55555555-5555-4555-8555-555555555555",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
