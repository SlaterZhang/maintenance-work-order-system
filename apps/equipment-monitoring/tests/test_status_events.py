import json
from pathlib import Path

from fastapi.testclient import TestClient

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLE_PATH = CONTRACTS_DIR / "examples" / "equipment-status-changed.json"
EVENT_PATH = "/api/v1/integration/equipment-status-events"
INTERNAL_TOKEN = "dev-internal-token-change-me"


def load_contract_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def post_event(client: TestClient, event: dict, trace_id: str | None = "trace-20260917-001",
               idem_key: str | None = None, token: str | None = INTERNAL_TOKEN) -> object:
    headers = {"Idempotency-Key": idem_key or event["eventId"]}
    if trace_id:
        headers["X-Trace-Id"] = trace_id
    if token is not None:
        headers["X-Internal-Token"] = token
    return client.post(EVENT_PATH, json=event, headers=headers)


def test_contract_example_accepted(client: TestClient):
    event = load_contract_example()
    response = post_event(client, event)
    assert response.status_code == 202
    body = response.json()
    assert body == {"accepted": True, "duplicate": False, "traceId": "trace-20260917-001"}

    equipment = client.get("/api/v1/equipment/EQ-000001").json()
    assert equipment["currentStatus"] == "MAINTAINING"
    assert equipment["version"] == 1


def test_duplicate_event_id_is_idempotent(client: TestClient):
    event = load_contract_example()
    first = post_event(client, event)
    assert first.status_code == 202
    assert first.json()["duplicate"] is False

    second = post_event(client, event)
    assert second.status_code == 202
    assert second.json()["duplicate"] is True

    equipment = client.get("/api/v1/equipment/EQ-000001").json()
    assert equipment["currentStatus"] == "MAINTAINING"
    assert equipment["version"] == 1


def test_rejects_unsupported_schema_version(client: TestClient):
    event = load_contract_example()
    event["schemaVersion"] = "1.0"
    response = post_event(client, event)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_rejects_missing_payload_field(client: TestClient):
    event = load_contract_example()
    del event["payload"]["operatorId"]
    response = post_event(client, event)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_rejects_invalid_target_status(client: TestClient):
    event = load_contract_example()
    event["payload"]["targetStatus"] = "FLYING"
    response = post_event(client, event)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_rejects_invalid_order_id_pattern(client: TestClient):
    event = load_contract_example()
    event["payload"]["orderId"] = "order-1"
    response = post_event(client, event)
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_rejects_idempotency_key_mismatch(client: TestClient):
    event = load_contract_example()
    response = post_event(client, event, idem_key="not-the-event-id")
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_MISMATCH"


def test_unknown_equipment_returns_404(client: TestClient):
    event = load_contract_example()
    event["payload"]["equipmentId"] = "EQ-999999"
    response = post_event(client, event)
    assert response.status_code == 404
    assert response.json()["code"] == "EQUIPMENT_NOT_FOUND"


def test_missing_trace_id_is_generated(client: TestClient):
    event = load_contract_example()
    event["eventId"] = "9a80c0e5-6c97-437f-afb7-65cb9fd9e003"
    response = post_event(client, event, trace_id=None)
    assert response.status_code == 202
    assert response.json()["traceId"]


def test_invalid_internal_token_rejected(client: TestClient):
    event = load_contract_example()
    response = post_event(client, event, token="wrong-token")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
