from __future__ import annotations

import json

from conftest import REPOSITORY_ROOT


def contract_event() -> dict:
    path = REPOSITORY_ROOT / "contracts" / "examples" / "equipment-status-changed.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_contract_event_is_idempotent_without_duplicate_side_effect(
    app, client, internal_headers
) -> None:
    event = contract_event()

    first = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=internal_headers,
    )
    duplicate = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=internal_headers,
    )

    assert first.status_code == duplicate.status_code == 202
    assert first.json() == {
        "accepted": True,
        "duplicate": False,
        "traceId": "trace-20260917-001",
    }
    assert duplicate.json()["duplicate"] is True
    detail = client.get("/api/v1/equipment/EQ-000001").json()
    assert detail["currentStatus"] == "MAINTAINING"
    assert detail["version"] == 1
    assert app.state.repository.count_status_events(event["eventId"]) == 1


def test_status_event_validates_equipment_and_trace_id(client, internal_headers) -> None:
    event = contract_event()
    event["eventId"] = "12345678-1234-4234-8234-123456789012"
    event["payload"]["equipmentId"] = "EQ-999999"

    missing = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=internal_headers,
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "EQUIPMENT_NOT_FOUND"

    event["payload"]["equipmentId"] = "EQ-000001"
    mismatch_headers = dict(internal_headers)
    mismatch_headers["Idempotency-Key"] = "12121212-1212-4212-8212-121212121212"
    mismatch_headers["X-Trace-Id"] = "trace-different-001"
    mismatch = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=mismatch_headers,
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "VALIDATION_ERROR"


def test_status_event_rejects_invalid_enum_and_internal_token(
    client, internal_headers
) -> None:
    event = contract_event()
    event["payload"]["targetStatus"] = "OFFLINE"
    invalid = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=internal_headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "VALIDATION_ERROR"

    event = contract_event()
    unauthorized_headers = dict(internal_headers)
    unauthorized_headers["X-Internal-Token"] = "wrong-token"
    unauthorized = client.post(
        "/api/v1/integration/equipment-status-events",
        json=event,
        headers=unauthorized_headers,
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "AUTH_TOKEN_INVALID"
