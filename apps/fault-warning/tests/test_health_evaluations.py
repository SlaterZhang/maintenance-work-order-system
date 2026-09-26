import re
import uuid

from fastapi.testclient import TestClient

SAMPLE = {
    "sampleId": "e51d94ca-5258-4e5a-bccc-99c55cfda001",
    "measuredAt": "2026-09-17T08:29:50Z",
    "temperatureC": 78.5,
    "vibrationMmS": 6.2,
    "currentA": 13.8,
    "rotationalSpeedRpm": 1450,
}
HEADERS = {
    "X-Internal-Token": "dev-internal-token-change-me",
    "X-Trace-Id": "trace-20260917-001",
}


def make_request(evaluation_id=None, sample=None, equipment_id="EQ-000001") -> dict:
    return {
        "evaluationId": evaluation_id or str(uuid.uuid4()),
        "equipmentId": equipment_id,
        "requestedAt": "2026-09-17T08:29:55Z",
        "sample": sample or dict(SAMPLE),
    }


def post_eval(client: TestClient, request: dict, idem_key: str | None = None):
    headers = dict(HEADERS)
    headers["Idempotency-Key"] = idem_key or request["evaluationId"]
    return client.post("/api/v1/health-evaluations", json=request, headers=headers)


def test_high_risk_creates_warning(client: TestClient):
    response = post_eval(client, make_request())
    assert response.status_code == 200
    body = response.json()
    assert body["riskLevel"] == "HIGH"
    assert body["healthScore"] == 42.7
    assert body["warningId"]
    assert re.fullmatch(r"WARN-[0-9]{8}-[0-9]{4}", body["warningId"])
    assert body["modelVersion"]
    assert body["evaluatedAt"].endswith("Z")
    assert body["suspectedFault"]
    assert body["recommendedAction"]
    assert body["evaluationId"]
    assert body["equipmentId"] == "EQ-000001"


def test_same_evaluation_id_is_idempotent(client: TestClient):
    request = make_request()
    first = post_eval(client, request)
    second = post_eval(client, request)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_same_equipment_reuses_warning_id(client: TestClient):
    first = post_eval(client, make_request())
    worse = dict(SAMPLE)
    worse["vibrationMmS"] = 8.0
    second = post_eval(client, make_request(sample=worse))
    assert first.json()["warningId"] == second.json()["warningId"]


def test_normal_sample_has_no_warning(client: TestClient):
    normal = dict(SAMPLE)
    normal.update({"temperatureC": 65.0, "vibrationMmS": 3.0, "currentA": 10.0})
    response = post_eval(client, make_request(sample=normal))
    assert response.status_code == 200
    body = response.json()
    assert body["riskLevel"] == "LOW"
    assert body["warningId"] is None


def test_invalid_equipment_id_rejected(client: TestClient):
    response = post_eval(client, make_request(equipment_id="BAD-ID"))
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_sample_out_of_range_rejected(client: TestClient):
    bad = dict(SAMPLE)
    bad["temperatureC"] = 300.0
    response = post_eval(client, make_request(sample=bad))
    assert response.status_code == 400


def test_idempotency_key_mismatch(client: TestClient):
    request = make_request()
    response = post_eval(client, request, idem_key="other-key")
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_MISMATCH"


def test_invalid_token_rejected(client: TestClient):
    request = make_request()
    headers = {"X-Internal-Token": "wrong-token", "Idempotency-Key": request["evaluationId"]}
    response = client.post("/api/v1/health-evaluations", json=request, headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
