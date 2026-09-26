"""B-API-01/02/03：预警分页查询、详情与确认"""
import uuid

TOKEN = "dev-internal-token-change-me"


def _raise_warning(client, equipment_id="EQ-000001"):
    evaluation_id = str(uuid.uuid4())
    body = {
        "evaluationId": evaluation_id,
        "equipmentId": equipment_id,
        "requestedAt": "2026-09-26T08:00:00Z",
        "sample": {
            "sampleId": str(uuid.uuid4()),
            "measuredAt": "2026-09-26T07:59:55Z",
            "temperatureC": 92.0,
            "vibrationMmS": 8.5,
            "currentA": 18.2,
            "rotationalSpeedRpm": 1450,
        },
    }
    r = client.post(
        "/api/v1/health-evaluations",
        json=body,
        headers={
            "X-Internal-Token": TOKEN,
            "X-Trace-Id": "trace-b-query-0001",
            "Idempotency-Key": evaluation_id,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def _ack(client, warning_id, expected_version, operator="USER-C-002",
         comment=None):
    body = {"operatorId": operator, "expectedVersion": expected_version}
    if comment is not None:
        body["comment"] = comment
    return client.post(
        f"/api/v1/warnings/{warning_id}/acknowledgements",
        json=body,
        headers={
            "X-Trace-Id": "trace-b-ack-0001",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )


# ---------- B-API-01 分页查询 ----------
def test_list_warnings_contains_raised(client):
    result = _raise_warning(client)
    r = client.get("/api/v1/warnings?pageSize=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    item = next(
        w for w in data["items"]
        if w["warningId"] == result["warningId"]
    )
    assert item["equipmentId"] == "EQ-000001"
    assert item["riskLevel"] == "CRITICAL"
    assert item["status"] == "OPEN"
    assert item["linkedOrderId"] is None
    assert item["acknowledgedBy"] is None


def test_list_warnings_filter_and_pagination(client):
    _raise_warning(client, "EQ-000001")
    r = client.get("/api/v1/warnings?equipmentId=EQ-000001&status=OPEN"
                   "&pageSize=1&page=1")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["equipmentId"] == "EQ-000001"

    r2 = client.get("/api/v1/warnings?equipmentId=EQ-000003")
    assert r2.status_code == 200
    assert r2.json()["total"] == 0


# ---------- B-API-02 详情 ----------
def test_get_warning_detail(client):
    result = _raise_warning(client)
    r = client.get(f"/api/v1/warnings/{result['warningId']}")
    assert r.status_code == 200
    data = r.json()
    assert data["warningId"] == result["warningId"]
    assert data["suspectedFault"]
    assert data["recommendedAction"]
    assert data["modelVersion"] == "rule-engine-1.0.0"
    assert data["version"] == 0


def test_get_warning_not_found(client):
    r = client.get("/api/v1/warnings/WARN-20260926-9999")
    assert r.status_code == 404
    assert r.json()["code"] == "WARNING_NOT_FOUND"


# ---------- B-API-03 确认 ----------
def test_acknowledge_warning_open_to_acknowledged(client):
    result = _raise_warning(client)
    r = _ack(client, result["warningId"], expected_version=0)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ACKNOWLEDGED"
    assert data["acknowledgedBy"] == "USER-C-002"
    assert data["acknowledgedAt"]
    assert data["version"] == 1


def test_acknowledge_version_conflict_409(client):
    result = _raise_warning(client)
    r = _ack(client, result["warningId"], expected_version=99)
    assert r.status_code == 409
    assert r.json()["code"] == "CONFLICT"


def test_acknowledge_twice_conflict_409(client):
    result = _raise_warning(client)
    assert _ack(client, result["warningId"], 0).status_code == 200
    r = _ack(client, result["warningId"], 1)
    assert r.status_code == 409
    assert r.json()["code"] == "CONFLICT"


def test_acknowledge_not_found(client):
    r = _ack(client, "WARN-20260926-9999", 0)
    assert r.status_code == 404
    assert r.json()["code"] == "WARNING_NOT_FOUND"
