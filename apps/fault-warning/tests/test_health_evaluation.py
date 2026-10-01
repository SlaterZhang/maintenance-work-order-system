"""C-INT-02 健康评估接口测试。

覆盖：风险评估分段、WarningId 生成与去重、事件外送与 outbox 重试、
幂等语义、鉴权与字段校验。
"""

import uuid

import pytest

from src.application import event_dispatch
from src.domain import models
from src.domain.enums import OutboxStatus
from src.interfaces.clients import member_a, member_c
from tests.conftest import (
    EQUIPMENT_ID,
    TRACE_ID,
    health_body,
    internal_headers,
    sample_payload,
)

URL = "/api/v1/health-evaluations"

# 健康分 100 -> LOW
NOMINAL_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=1.0, currentA=10.0, rotationalSpeedRpm=1500.0
)
# 健康分 76 -> MEDIUM（振动 4.8 mm/s）
MEDIUM_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=4.8, currentA=10.0, rotationalSpeedRpm=1500.0
)
# 健康分 49.4 -> HIGH（契约示例样本）
HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)
# 健康分 0 -> CRITICAL
CRITICAL_SAMPLE = dict(
    temperatureC=249.0, vibrationMmS=199.0, currentA=9999.0,
    rotationalSpeedRpm=100000.0,
)


def _post(client, body, key=None, **header_overrides):
    headers = internal_headers(key, **header_overrides)
    return client.post(URL, json=body, headers=headers)


# ---------- 正向流程 ----------
def test_high_risk_creates_warning(client):
    body = health_body(sample=sample_payload(**HIGH_SAMPLE))
    response = _post(client, body)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["evaluationId"] == body["evaluationId"]
    assert data["equipmentId"] == EQUIPMENT_ID
    assert data["riskLevel"] == "HIGH"
    assert data["healthScore"] == 49.4
    assert data["suspectedFault"] == "主轴轴承振动异常"
    assert data["warningId"].startswith("WARN-")
    assert data["modelVersion"] == "rule-engine-1.0.0"
    assert data["evaluatedAt"].endswith("Z")


@pytest.mark.parametrize(
    "sample,expected_risk,expects_warning",
    [
        (NOMINAL_SAMPLE, "LOW", False),
        (MEDIUM_SAMPLE, "MEDIUM", False),
        (HIGH_SAMPLE, "HIGH", True),
        (CRITICAL_SAMPLE, "CRITICAL", True),
    ],
)
def test_risk_segments_drive_warning_creation(
    client, sample, expected_risk, expects_warning
):
    """只有 HIGH / CRITICAL 才生成 WarningId 并向 C 发事件。"""
    response = _post(client, health_body(sample=sample_payload(**sample)))
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["riskLevel"] == expected_risk
    if expects_warning:
        assert data["warningId"] is not None
    else:
        # 契约要求可空字段显式返回 null
        assert data["warningId"] is None


def test_no_warning_means_no_event_sent(client, captured_events):
    _post(client, health_body(sample=sample_payload(**NOMINAL_SAMPLE)))
    _post(client, health_body(sample=sample_payload(**MEDIUM_SAMPLE)))
    assert captured_events == []


def test_warning_is_linked_to_order_after_c_accepts(client, db, captured_events):
    """C 返回 orderId 后，预警回填 linkedOrderId 并进入 LINKED_TO_ORDER。"""
    response = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))
    warning_id = response.json()["warningId"]

    warning = (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )
    assert warning.linked_order_id == "WO-20260917-0001"
    assert warning.status == "LINKED_TO_ORDER"
    assert warning.version == 1


# ---------- WarningId 去重 ----------
def test_repeated_evaluation_reuses_warning_id(client, captured_events):
    """同一设备同一疑似故障重复评估不产生重复 WarningId，也不重复发事件。"""
    first = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))
    second = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))

    assert first.json()["warningId"] == second.json()["warningId"]
    assert len(captured_events) == 1


def test_different_fault_on_same_equipment_creates_new_warning(client):
    """同一设备但疑似故障不同 -> 新的 WarningId。"""
    bearing = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))
    overheat = _post(
        client,
        health_body(
            sample=sample_payload(
                temperatureC=95.0, vibrationMmS=1.0, currentA=1.0,
                rotationalSpeedRpm=1500.0,
            )
        ),
    )

    assert bearing.json()["warningId"] != overheat.json()["warningId"]


def test_warning_ids_are_sequential_and_unique(client, db):
    """WarningId 序号按当日递增，不使用随机数，不会碰撞。"""
    for _ in range(3):
        _post(
            client,
            health_body(
                sample=sample_payload(
                    temperatureC=95.0, vibrationMmS=1.0, currentA=1.0,
                    rotationalSpeedRpm=1500.0,
                )
            ),
        )
        # 每次换一个设备，避免被去重规则合并
    ids = [
        row.warning_id
        for row in db.query(models.Warning).order_by(models.Warning.id).all()
    ]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


# ---------- 事件报文 ----------
def test_emitted_event_matches_contract_example_structure(client, captured_events):
    _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))

    assert len(captured_events) == 1
    event = captured_events[0]

    assert set(event) == {
        "eventId",
        "eventType",
        "schemaVersion",
        "occurredAt",
        "sourceMember",
        "traceId",
        "payload",
    }
    assert event["eventType"] == "WarningRaised"
    assert event["sourceMember"] == "MEMBER_B"
    assert event["schemaVersion"] == "2.0"
    assert event["traceId"] == TRACE_ID
    uuid.UUID(event["eventId"])  # 必须是合法 UUID

    payload = event["payload"]
    assert set(payload) == {
        "warningId",
        "equipmentId",
        "riskLevel",
        "healthScore",
        "suspectedFault",
        "recommendedAction",
        "warningAt",
        "modelVersion",
        "metricSnapshot",
    }
    assert set(payload["metricSnapshot"]) == {
        "sampleId",
        "measuredAt",
        "temperatureC",
        "vibrationMmS",
        "currentA",
        "rotationalSpeedRpm",
    }


def test_emitted_event_carries_the_submitted_sample(client, captured_events):
    sample = sample_payload(**HIGH_SAMPLE)
    _post(client, health_body(sample=sample))

    snapshot = captured_events[0]["payload"]["metricSnapshot"]
    assert snapshot["sampleId"] == sample["sampleId"]
    assert snapshot["temperatureC"] == sample["temperatureC"]
    assert snapshot["vibrationMmS"] == sample["vibrationMmS"]
    assert snapshot["measuredAt"] == "2026-09-17T08:29:50Z"


# ---------- outbox：投递失败不回滚业务 ----------
def test_unreachable_c_keeps_warning_and_queues_event(client, db, monkeypatch):
    """C 不可达时：预警仍然成立，事件留在 outbox 待重试。"""

    def failing_send(event, trace_id, event_id):
        return False, None, "ConnectError: 连接被拒绝"

    monkeypatch.setattr(member_c, "send_warning_raised", failing_send)

    response = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))
    assert response.status_code == 200
    warning_id = response.json()["warningId"]

    warning = (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )
    assert warning.status == "OPEN"          # 没有被回滚
    assert warning.linked_order_id is None

    queued = db.query(models.OutboxEvent).all()
    assert len(queued) == 1
    assert queued[0].status == OutboxStatus.PENDING.value
    assert queued[0].attempts == 1
    assert "连接被拒绝" in queued[0].last_error


def test_outbox_retry_delivers_and_links_order(client, db, monkeypatch):
    """C 恢复后重试投递成功，并回填 linkedOrderId。"""

    def failing_send(event, trace_id, event_id):
        return False, None, "ConnectError: 连接被拒绝"

    monkeypatch.setattr(member_c, "send_warning_raised", failing_send)
    response = _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))
    warning_id = response.json()["warningId"]

    def healthy_send(event, trace_id, event_id):
        return True, {"accepted": True, "orderId": "WO-20260917-0007"}, None

    monkeypatch.setattr(member_c, "send_warning_raised", healthy_send)
    summary = event_dispatch.dispatch_pending_events(db)

    assert summary["sent"] == 1
    db.expire_all()
    queued = db.query(models.OutboxEvent).one()
    assert queued.status == OutboxStatus.SENT.value

    warning = (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )
    assert warning.linked_order_id == "WO-20260917-0007"
    assert warning.status == "LINKED_TO_ORDER"


def test_outbox_gives_up_after_max_attempts(client, db, monkeypatch):
    """连续失败达到上限后置 FAILED，不再无限重试。"""
    monkeypatch.setattr(
        member_c,
        "send_warning_raised",
        lambda event, trace_id, event_id: (False, None, "boom"),
    )
    _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)))

    monkeypatch.setattr(
        member_c, "send_warning_raised",
        lambda event, trace_id, event_id: (False, None, "still boom"),
    )
    event_dispatch.dispatch_pending_events(db)
    event_dispatch.dispatch_pending_events(db)

    db.expire_all()
    queued = db.query(models.OutboxEvent).one()
    assert queued.status == OutboxStatus.FAILED.value
    assert queued.attempts == 3


# ---------- 幂等 ----------
def test_same_idempotency_key_returns_cached_response(client, db):
    body = health_body(sample=sample_payload(**HIGH_SAMPLE))
    key = str(uuid.uuid4())

    first = _post(client, body, key=key)
    second = _post(client, body, key=key)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()
    assert db.query(models.HealthEvaluation).count() == 1
    assert db.query(models.Warning).count() == 1


def test_same_idempotency_key_different_body_conflicts(client):
    key = str(uuid.uuid4())
    _post(client, health_body(sample=sample_payload(**HIGH_SAMPLE)), key=key)
    response = _post(
        client, health_body(sample=sample_payload(**CRITICAL_SAMPLE)), key=key
    )

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_same_evaluation_id_is_naturally_idempotent(client, db):
    """同一 evaluationId 重复提交（换幂等键）返回首次结果，不重复评分。"""
    evaluation_id = str(uuid.uuid4())
    first = _post(client, health_body(evaluationId=evaluation_id))
    second = _post(
        client,
        health_body(evaluationId=evaluation_id, sample=sample_payload(**NOMINAL_SAMPLE)),
    )

    assert first.json() == second.json()
    assert db.query(models.HealthEvaluation).count() == 1


def test_missing_idempotency_key_is_validation_error(client):
    response = client.post(
        URL,
        json=health_body(),
        headers={"X-Internal-Token": "test-internal-token", "X-Trace-Id": TRACE_ID},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_non_uuid_idempotency_key_is_rejected(client):
    response = _post(client, health_body(), key="not-a-uuid")
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------- 鉴权 ----------
def test_missing_internal_token_returns_401(client):
    response = client.post(
        URL,
        json=health_body(),
        headers={
            "X-Trace-Id": TRACE_ID,
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_INVALID"


def test_wrong_internal_token_returns_401(client):
    response = _post(client, health_body(), **{"X-Internal-Token": "wrong"})
    assert response.status_code == 401


def test_missing_trace_id_is_rejected(client):
    """C-INT-02 使用 RequiredTraceIdHeader，缺 X-Trace-Id 必须 400。"""
    response = client.post(
        URL,
        json=health_body(),
        headers={
            "X-Internal-Token": "test-internal-token",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "X-Trace-Id"


# ---------- 设备校验 ----------
def test_unknown_equipment_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        member_a, "get_equipment", lambda equipment_id, trace_id: None
    )
    response = _post(client, health_body())
    assert response.status_code == 404
    assert response.json()["code"] == "EQUIPMENT_NOT_FOUND"


def test_equipment_service_down_fails_closed(client, monkeypatch):
    """A 不可达且未开启 mock 时返回 500，不伪造设备。"""
    from src.domain.errors import InternalError

    def boom(equipment_id, trace_id):
        raise InternalError("无法访问设备服务（C-INT-01），评估未完成")

    monkeypatch.setattr(member_a, "get_equipment", boom)
    response = _post(client, health_body())
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


# ---------- 字段校验 ----------
@pytest.mark.parametrize(
    "mutate,expected_field",
    [
        (lambda b: b.pop("equipmentId"), "equipmentId"),
        (lambda b: b.__setitem__("equipmentId", "EQ-1"), "equipmentId"),
        (lambda b: b.pop("requestedAt"), "requestedAt"),
        (lambda b: b.__setitem__("requestedAt", "2026/09/17 08:29:55"), "requestedAt"),
        (lambda b: b.__setitem__("extraField", 1), "extraField"),
        (lambda b: b.pop("evaluationId"), "evaluationId"),
        (lambda b: b.__setitem__("evaluationId", "not-a-uuid"), "evaluationId"),
    ],
)
def test_envelope_field_validation(client, mutate, expected_field):
    body = health_body()
    mutate(body)

    response = _post(client, body)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert expected_field in {item["field"] for item in payload["details"]}


@pytest.mark.parametrize(
    "mutate,expected_field",
    [
        (lambda b: b["sample"].__setitem__("temperatureC", 300.0), "sample.temperatureC"),
        (lambda b: b["sample"].__setitem__("temperatureC", -100.0), "sample.temperatureC"),
        (lambda b: b["sample"].__setitem__("vibrationMmS", -1.0), "sample.vibrationMmS"),
        (lambda b: b["sample"].__setitem__("currentA", 20000.0), "sample.currentA"),
        (lambda b: b["sample"].__setitem__("rotationalSpeedRpm", -5.0), "sample.rotationalSpeedRpm"),
        (lambda b: b["sample"].pop("sampleId"), "sample.sampleId"),
        (lambda b: b["sample"].__setitem__("unknown", 1), "sample.unknown"),
        (lambda b: b.__setitem__("sample", "not-an-object"), "sample"),
    ],
)
def test_sample_field_validation(client, mutate, expected_field):
    body = health_body()
    mutate(body)

    response = _post(client, body)
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert expected_field in {item["field"] for item in payload["details"]}


def test_all_field_errors_reported_together(client):
    """校验是累积式的：一次返回所有字段问题，而不是只报第一个。"""
    body = health_body(equipmentId="bad", requestedAt="bad")
    body["sample"]["temperatureC"] = 999.0

    response = _post(client, body)
    assert response.status_code == 400
    fields = {item["field"] for item in response.json()["details"]}
    assert {"equipmentId", "requestedAt", "sample.temperatureC"} <= fields


def test_error_response_shape_matches_contract(client):
    response = client.post(
        URL,
        json=health_body(),
        headers={"X-Trace-Id": TRACE_ID},
    )
    body = response.json()
    assert set(body) == {"code", "message", "traceId", "timestamp", "details"}
    assert body["traceId"] == TRACE_ID
    assert body["timestamp"].endswith("Z")
    assert isinstance(body["details"], list)


def test_health_probe(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "member-b"
