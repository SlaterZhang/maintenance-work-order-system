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
def _seed_ids() -> set[str]:
    from src.infrastructure.seed import SEED_EQUIPMENT

    return {item["equipment_id"] for item in SEED_EQUIPMENT}


def _seed_status_count(status: str) -> int:
    from src.infrastructure.seed import SEED_EQUIPMENT

    return sum(1 for item in SEED_EQUIPMENT
               if item["current_status"] == status)


def test_list_equipment_seeded(client):
    """种子设备全量可见（数量与清单随 SEED_EQUIPMENT 演进，不写死）。"""
    expected = _seed_ids()
    r = client.get("/api/v1/equipment?pageSize=100")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == len(expected)
    assert data["page"] == 1 and data["pageSize"] == 100
    assert data["totalPages"] == 1
    ids = {item["equipmentId"] for item in data["items"]}
    assert ids == expected


def test_seed_statuses_do_not_imply_other_aggregates(client):
    """种子设备的运行状态不得隐含 B/C 的聚合数据。

    ``MAINTAINING`` 意味着存在维修工单、``WARNING`` 意味着存在活跃预警，
    但重置后 B/C 都是空的。若种子播这两种状态，看板会显示"维修中"却在
    工单列表里找不到对应工单——自相矛盾的演示现场。
    """
    from src.infrastructure.seed import SEED_EQUIPMENT

    forbidden = {"MAINTAINING", "WARNING"}
    offending = {
        item["equipment_id"]: item["current_status"]
        for item in SEED_EQUIPMENT
        if item["current_status"] in forbidden
    }
    assert offending == {}, (
        f"种子状态 {offending} 隐含其它模块的聚合数据，"
        "重置后会造成前后台不一致；请改用 RUNNING/STOPPED/TRIAL_RUNNING，"
        "或同步在 B/C 播种对应数据。"
    )


def test_seed_covers_multiple_lines_and_types(client):
    """种子须铺开产线与设备类型，使台账/看板的分组视图有内容可展示。"""
    from src.infrastructure.seed import SEED_EQUIPMENT

    lines = {item["production_line_id"] for item in SEED_EQUIPMENT}
    types = {item["equipment_type"] for item in SEED_EQUIPMENT}
    statuses = {item["current_status"] for item in SEED_EQUIPMENT}
    assert len(lines) >= 4
    assert len(types) >= 6
    assert {"RUNNING", "STOPPED", "TRIAL_RUNNING"} <= statuses
    # 每台设备的必填档案字段齐全（档案页/台账页直接展示）
    for item in SEED_EQUIPMENT:
        for field in ("equipment_id", "name", "equipment_type",
                      "production_line_id", "location", "manufacturer",
                      "model", "responsible_department"):
            assert item.get(field), f"{item['equipment_id']} 缺 {field}"


def test_list_equipment_filter_by_status(client):
    """按运行状态过滤：数量与 SEED_EQUIPMENT 中该状态台数一致。"""
    expected = _seed_status_count("RUNNING")
    r = client.get("/api/v1/equipment?status=RUNNING&pageSize=100")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == expected >= 1
    assert all(item["currentStatus"] == "RUNNING" for item in data["items"])
    names = {item["equipmentId"]: item["name"] for item in data["items"]}
    assert names["EQ-000001"] == "一号数控机床"


def test_list_equipment_keyword_and_pagination(client):
    """keyword=EQ-0000 命中全部种子设备，分页切片正确。"""
    total = len(_seed_ids())
    r = client.get("/api/v1/equipment?keyword=EQ-0000&pageSize=2&page=2")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == total
    assert data["totalPages"] == (total + 1) // 2
    assert len(data["items"]) == min(2, total - 2)


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
    # 阶段3：种子 72 小时遥测历史 + 本测试新投递的 2 条
    assert data["total"] == 2 + 72
    times = [item["measuredAt"] for item in data["items"]]
    assert times == sorted(times, reverse=True)


def test_seed_telemetry_history_present(client):
    """阶段3：种子自带 72 小时缓变历史（趋势预测演示数据），且无随机。"""
    from src.infrastructure.seed import SEED_TELEMETRY_PROFILES, HISTORY_HOURS

    r = client.get("/api/v1/equipment/EQ-000001/telemetry?pageSize=100")
    data = r.json()
    assert data["total"] == HISTORY_HOURS
    items = sorted(data["items"], key=lambda x: x["measuredAt"])  # 升序
    # 首样本等于基线起点，末样本等于起点 + 71×每小时增量
    prof = SEED_TELEMETRY_PROFILES["EQ-000001"]
    assert items[0]["temperatureC"] == prof["temperature"][0]
    assert items[-1]["temperatureC"] == round(
        prof["temperature"][0] + prof["temperature"][1] * (HISTORY_HOURS - 1), 2)
    # 温度序列单调上行（退化叙事成立）
    temps = [it["temperatureC"] for it in items]
    assert temps == sorted(temps)


def test_list_telemetry_unknown_equipment_404(client):
    r = client.get("/api/v1/equipment/EQ-999999/telemetry")
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"
