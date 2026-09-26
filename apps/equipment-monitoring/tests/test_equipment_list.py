"""A-API-01/04/05：设备分页查询与运行数据接口"""
import uuid

from src.config import settings

TOKEN = settings.internal_api_token
HEADERS = {"X-Internal-Token": TOKEN, "X-Trace-Id": "trace-a-list-0001"}


def _batch(samples=None, batch_id=None):
    return {
        "batchId": batch_id or str(uuid.uuid4()),
        "source": "SIMULATOR",
        "samples": samples or [{
            "sampleId": str(uuid.uuid4()),
            "measuredAt": "2026-09-26T08:00:00Z",
            "temperatureC": 78.5,
            "vibrationMmS": 6.2,
            "currentA": 13.8,
            "rotationalSpeedRpm": 1450,
        }],
    }


def _post_telemetry(client, equipment_id, body):
    return client.post(
        f"/api/v1/equipment/{equipment_id}/telemetry",
        json=body,
        headers={**HEADERS, "Idempotency-Key": body["batchId"]},
    )


# ---------- A-API-01 设备分页查询 ----------
def test_list_equipment_seeded(client):
    r = client.get("/api/v1/equipment?pageSize=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["page"] == 1 and data["pageSize"] == 10
    assert data["totalPages"] == 1
    ids = {item["equipmentId"] for item in data["items"]}
    assert ids == {"EQ-000001", "EQ-000002", "EQ-000003"}


def test_list_equipment_filter_by_status(client):
    r = client.get("/api/v1/equipment?status=RUNNING")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["equipmentId"] == "EQ-000001"
    assert data["items"][0]["name"] == "一号数控机床"


def test_list_equipment_keyword_and_pagination(client):
    r = client.get("/api/v1/equipment?keyword=EQ-0000&pageSize=2&page=2")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["totalPages"] == 2
    assert len(data["items"]) == 1


# ---------- A-API-05 批量注入 ----------
def test_ingest_telemetry_accepts_samples(client):
    body = _batch(samples=[
        {"sampleId": str(uuid.uuid4()),
         "measuredAt": "2026-09-26T08:00:00Z",
         "temperatureC": 78.5, "vibrationMmS": 6.2,
         "currentA": 13.8, "rotationalSpeedRpm": 1450},
        {"sampleId": str(uuid.uuid4()),
         "measuredAt": "2026-09-26T08:00:05Z",
         "temperatureC": 79.1, "vibrationMmS": 6.4,
         "currentA": 14.0, "rotationalSpeedRpm": 1455},
        {"sampleId": str(uuid.uuid4()),
         "measuredAt": "2026-09-26T08:00:10Z",
         "temperatureC": 92.0, "vibrationMmS": 8.5,
         "currentA": 18.2, "rotationalSpeedRpm": 1450},
    ])
    r = _post_telemetry(client, "EQ-000001", body)
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["acceptedCount"] == 3
    assert data["rejectedCount"] == 0
    assert data["duplicate"] is False
    assert data["equipmentId"] == "EQ-000001"

    r2 = _post_telemetry(client, "EQ-000001", _batch(batch_id=body["batchId"]))
    assert r2.status_code == 202
    assert r2.json()["duplicate"] is True
    assert r2.json()["acceptedCount"] == 3


def test_ingest_telemetry_unknown_equipment_404(client):
    r = _post_telemetry(client, "EQ-999999", _batch())
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"


def test_ingest_telemetry_invalid_range_400(client):
    body = _batch(samples=[{
        "sampleId": str(uuid.uuid4()),
        "measuredAt": "2026-09-26T08:00:00Z",
        "temperatureC": 999.0,
        "vibrationMmS": 6.2,
        "currentA": 13.8,
        "rotationalSpeedRpm": 1450,
    }])
    r = _post_telemetry(client, "EQ-000001", body)
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


# ---------- A-API-04 查询运行数据 ----------
def test_list_telemetry_returns_desc(client):
    batch = _batch(samples=[
        {"sampleId": str(uuid.uuid4()),
         "measuredAt": "2026-09-26T09:00:00Z",
         "temperatureC": 80.0, "vibrationMmS": 6.0,
         "currentA": 14.0, "rotationalSpeedRpm": 1400},
        {"sampleId": str(uuid.uuid4()),
         "measuredAt": "2026-09-26T09:00:05Z",
         "temperatureC": 81.0, "vibrationMmS": 6.1,
         "currentA": 14.1, "rotationalSpeedRpm": 1410},
    ])
    assert _post_telemetry(client, "EQ-000002", batch).status_code == 202

    r = client.get("/api/v1/equipment/EQ-000002/telemetry")
    assert r.status_code == 200
    data = r.json()
    assert data["equipmentId"] == "EQ-000002"
    assert data["total"] == 2
    times = [item["measuredAt"] for item in data["items"]]
    assert times == sorted(times, reverse=True)


def test_list_telemetry_unknown_equipment_404(client):
    r = client.get("/api/v1/equipment/EQ-999999/telemetry")
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"
