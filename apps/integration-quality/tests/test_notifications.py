import uuid

from fastapi.testclient import TestClient

NOTIFICATION_PATH = "/api/v1/notifications"
HEADERS = {
    "X-Internal-Token": "dev-internal-token-change-me",
    "X-Trace-Id": "trace-20260917-001",
}


def make_request(**overrides) -> dict:
    request = {
        "recipientUserIds": ["USER-C-002"],
        "templateCode": "WORK_ORDER_ASSIGNED",
        "channel": "IN_APP",
        "variables": {"orderId": "WO-20260917-0001"},
        "businessReference": "WO-20260917-0001",
    }
    request.update(overrides)
    return request


def post_notification(client: TestClient, request: dict, idem_key: str | None = None):
    headers = dict(HEADERS)
    headers["Idempotency-Key"] = idem_key or str(uuid.uuid4())
    return client.post(NOTIFICATION_PATH, json=request, headers=headers)


def test_submit_notification_accepted(client: TestClient):
    response = post_notification(client, make_request())
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["duplicate"] is False
    assert body["traceId"] == "trace-20260917-001"
    assert body["notificationId"].startswith("NOTICE-")


def test_same_idempotency_key_returns_same_notification(client: TestClient):
    key = str(uuid.uuid4())
    first = post_notification(client, make_request(), idem_key=key)
    second = post_notification(client, make_request(), idem_key=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["notificationId"] == second.json()["notificationId"]
    assert second.json()["duplicate"] is True


def test_sms_channel_rejected(client: TestClient):
    response = post_notification(client, make_request(channel="SMS"))
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_unknown_template_rejected(client: TestClient):
    response = post_notification(client, make_request(templateCode="NOT_A_TEMPLATE"))
    assert response.status_code == 400


def test_empty_recipients_rejected(client: TestClient):
    response = post_notification(client, make_request(recipientUserIds=[]))
    assert response.status_code == 400


def test_invalid_token_rejected(client: TestClient):
    headers = dict(HEADERS)
    headers["X-Internal-Token"] = "wrong-token"
    headers["Idempotency-Key"] = str(uuid.uuid4())
    response = client.post(NOTIFICATION_PATH, json=make_request(), headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
