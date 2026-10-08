"""C-INT-09 预警自动闭环测试（2026-10-07 新增）。

背景
----
用户现场：设备已"恢复正常数据"（EQ-000001 运行中、健康度 94.7），
但设备详情页「当前预警详情 WARN-20261007-0001」卡片常驻不消。

根因：``_obtain_warning`` 在非 HIGH/CRITICAL 时直接 ``return None, False``，
LOW 评估只落库、完全不碰已有预警；B 只建预警从不闭环。而"恢复正常数据"
走 A 的 ``simulate(NORMAL)`` → A 直接调 B 评估，不经过 C 的工单流程，
工单永远停在 ``PENDING_CONFIRMATION``，B 也永远收不到维修结论（C-INT-05），
预警就永久悬在 ``LINKED_TO_ORDER``。

修复口径（用户 2026-10-07 决策）
-------------------------------
* **LOW 单次即闭环**：最新评估为 LOW → 该设备全部活跃预警自动 RESOLVED；
* 同时发 ``WarningResolvedReported``（C-INT-09）通知 C 结掉悬空早期工单；
* MEDIUM / HIGH / CRITICAL 不触发自动闭环（只有"确认恢复"才闭环）。
"""

import uuid

import pytest

from src.application import event_dispatch
from src.domain import models
from src.domain.enums import OutboxStatus
from src.interfaces.clients import member_c
from tests.conftest import (
    EQUIPMENT_ID,
    TRACE_ID,
    health_body,
    internal_headers,
    sample_payload,
)

URL = "/api/v1/health-evaluations"

NOMINAL_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=1.0, currentA=10.0, rotationalSpeedRpm=1500.0
)
MEDIUM_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=4.8, currentA=10.0, rotationalSpeedRpm=1500.0
)
HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)


def _eval(client, sample):
    return client.post(
        URL,
        json=health_body(sample=sample_payload(**sample)),
        headers=internal_headers(),
    )


def _create_warning(client) -> str:
    """注入 HIGH 评估产生一条预警；C 接受后预警进入 LINKED_TO_ORDER。"""
    response = _eval(client, HIGH_SAMPLE)
    assert response.status_code == 200, response.text
    warning_id = response.json()["warningId"]
    assert warning_id, "HIGH 评估应产生预警"
    return warning_id


def _warning(db, warning_id: str) -> models.Warning:
    db.expire_all()
    return (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )


def _resolved_outbox(db) -> list[models.OutboxEvent]:
    db.expire_all()
    return (
        db.query(models.OutboxEvent)
        .filter(models.OutboxEvent.event_type == "WarningResolvedReported")
        .all()
    )


# ---------- 核心：LOW 单次即闭环 ----------
def test_low_evaluation_resolves_linked_warning(client, db, captured_resolutions):
    """用户场景回归：恢复后 LOW 评估必须把 LINKED_TO_ORDER 预警闭环。"""
    warning_id = _create_warning(client)
    linked = _warning(db, warning_id)
    assert linked.status == "LINKED_TO_ORDER"
    assert linked.linked_order_id == "WO-20260917-0001"
    version_before = linked.version

    response = _eval(client, NOMINAL_SAMPLE)
    assert response.status_code == 200, response.text
    data = response.json()
    # LOW 评估自身不建预警（既有契约不变）
    assert data["riskLevel"] == "LOW"
    assert data["warningId"] is None

    resolved = _warning(db, warning_id)
    assert resolved.status == "RESOLVED", "设备恢复后预警必须闭环"
    assert resolved.version == version_before + 1

    # C-INT-09 通知已发出，报文符合契约
    assert len(captured_resolutions) == 1
    event = captured_resolutions[0]
    assert event["eventType"] == "WarningResolvedReported"
    assert event["sourceMember"] == "MEMBER_B"
    assert event["traceId"] == TRACE_ID
    payload = event["payload"]
    assert payload["warningId"] == warning_id
    assert payload["equipmentId"] == EQUIPMENT_ID
    assert payload["healthScore"] == 100.0
    assert payload["resolvedBy"] == "USER-SYSTEM-AUTO"
    assert payload["linkedOrderId"] == "WO-20260917-0001"
    assert payload["resolvedAt"].endswith("Z")
    assert uuid.UUID(event["eventId"])  # eventId 是合法 UUID


def test_auto_resolve_records_history(client, db):
    warning_id = _create_warning(client)
    _eval(client, NOMINAL_SAMPLE)

    db.expire_all()
    history = (
        db.query(models.WarningStatusHistory)
        .filter(
            models.WarningStatusHistory.action == "AUTO_RESOLVE",
            models.WarningStatusHistory.trace_id == TRACE_ID,
        )
        .all()
    )
    assert history, "自动闭环必须留下审计记录"
    entry = history[-1]
    assert entry.from_status == "LINKED_TO_ORDER"
    assert entry.to_status == "RESOLVED"
    assert entry.operator_id == "USER-SYSTEM-AUTO"
    assert warning_id in (entry.detail or "")


def test_resolved_event_delivered_to_c_and_outbox_sent(client, db, captured_resolutions):
    _create_warning(client)
    _eval(client, NOMINAL_SAMPLE)

    rows = _resolved_outbox(db)
    assert len(rows) == 1
    assert rows[0].status == OutboxStatus.SENT.value
    assert rows[0].target_url.endswith("/api/v1/integration/warning-closures")
    assert rows[0].attempts == 1
    assert len(captured_resolutions) == 1


# ---------- 边界：只有 LOW 才闭环 ----------
@pytest.mark.parametrize("sample", [MEDIUM_SAMPLE, HIGH_SAMPLE])
def test_non_low_evaluation_does_not_resolve(client, db, sample):
    warning_id = _create_warning(client)
    version_before = _warning(db, warning_id).version

    _eval(client, sample)

    warning = _warning(db, warning_id)
    assert warning.status in ("LINKED_TO_ORDER", "OPEN"), warning.status
    assert warning.version == version_before
    assert _resolved_outbox(db) == []


def test_low_evaluation_without_active_warning_is_noop(client, db, captured_resolutions):
    response = _eval(client, NOMINAL_SAMPLE)
    assert response.status_code == 200, response.text
    assert response.json()["warningId"] is None
    assert _resolved_outbox(db) == []
    assert captured_resolutions == []


def test_low_evaluation_resolves_all_active_warnings_of_equipment(
    client, db, captured_resolutions
):
    """同一设备可能存在多条不同疑似故障的活跃预警，恢复时一并闭环。"""
    first_id = _create_warning(client)

    # 直接插入第二条活跃预警（模拟历史遗留的另一故障）
    db.add(models.Warning(
        warning_id="WARN-20260917-9002",
        equipment_id=EQUIPMENT_ID,
        risk_level="CRITICAL",
        health_score=20.0,
        suspected_fault="电机绕组过热",
        recommended_action="立即停机检修",
        status="OPEN",
        warning_at=__import__("datetime").datetime(2026, 9, 17, 9, 0, 0),
        model_version="rule-engine-1.0.0",
        version=0,
    ))
    db.commit()

    _eval(client, NOMINAL_SAMPLE)

    assert _warning(db, first_id).status == "RESOLVED"
    assert _warning(db, "WARN-20260917-9002").status == "RESOLVED"
    assert {e["payload"]["warningId"] for e in captured_resolutions} == {
        first_id,
        "WARN-20260917-9002",
    }


def test_terminal_warning_is_not_rewritten(client, db, captured_resolutions):
    """已取消/已解决的预警收到恢复评估：只留档，不反向改写。"""
    warning_id = _create_warning(client)

    # 先用工单取消把它闭环为 CANCELLED 终态
    cancel_body = {
        "eventId": str(uuid.uuid4()),
        "eventType": "OrderCancelledReported",
        "schemaVersion": "2.0",
        "occurredAt": "2026-10-07T12:05:00Z",
        "sourceMember": "MEMBER_C",
        "traceId": TRACE_ID,
        "payload": {
            "orderId": "WO-20260917-0001",
            "warningId": warning_id,
            "equipmentId": EQUIPMENT_ID,
            "cancelledAt": "2026-10-07T12:04:55Z",
            "cancelledBy": "USER-C-001",
            "reason": "测试终态守卫",
        },
    }
    response = client.post(
        "/api/v1/integration/order-cancellations",
        json=cancel_body,
        headers=internal_headers(),
    )
    assert response.status_code == 202, response.text
    cancelled = _warning(db, warning_id)
    assert cancelled.status == "CANCELLED"
    version_before = cancelled.version

    _eval(client, NOMINAL_SAMPLE)

    after = _warning(db, warning_id)
    assert after.status == "CANCELLED"
    assert after.version == version_before, "终态预警版本不得再推进"
    assert _resolved_outbox(db) == [], "终态预警不得再发闭环事件"


# ---------- 幂等与降级 ----------
def test_repeated_evaluation_id_replays_without_double_resolve(
    client, db, captured_resolutions
):
    warning_id = _create_warning(client)

    body = health_body(sample=sample_payload(**NOMINAL_SAMPLE))
    first = client.post(URL, json=body, headers=internal_headers())
    second = client.post(URL, json=body, headers=internal_headers())
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()

    assert _warning(db, warning_id).status == "RESOLVED"
    assert len(_resolved_outbox(db)) == 1, "幂等回放不得重复登记闭环事件"
    assert len(captured_resolutions) == 1


def test_delivery_failure_keeps_event_pending_for_retry(client, db, monkeypatch):
    """C 不可达时闭环仍然成立，事件留在 outbox 待重试。"""

    def failing_send(event, trace_id, event_id):
        return False, None, "ConnectError: 连接被拒绝"

    monkeypatch.setattr(member_c, "send_warning_resolved", failing_send)

    warning_id = _create_warning(client)
    _eval(client, NOMINAL_SAMPLE)

    assert _warning(db, warning_id).status == "RESOLVED"
    rows = _resolved_outbox(db)
    assert len(rows) == 1
    assert rows[0].status == OutboxStatus.PENDING.value
    assert rows[0].attempts == 1


def test_pending_resolution_retries_on_next_dispatch(client, db, monkeypatch):
    """故障恢复后再次投递，原事件成功且不再重复闭环。"""
    attempts = {"n": 0}
    delivered: list[dict] = []

    def flaky_send(event, trace_id, event_id):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return False, None, "ConnectError: 连接被拒绝"
        delivered.append(event)
        return True, {"accepted": True, "duplicate": False}, None

    monkeypatch.setattr(member_c, "send_warning_resolved", flaky_send)

    warning_id = _create_warning(client)
    _eval(client, NOMINAL_SAMPLE)
    assert _warning(db, warning_id).status == "RESOLVED"

    # 模拟下一次评估（LOW）触发 dispatch 重试
    _eval(client, NOMINAL_SAMPLE)

    rows = _resolved_outbox(db)
    assert len(rows) == 1, "重试不得再登记新事件"
    assert rows[0].status == OutboxStatus.SENT.value
    assert len(delivered) == 1


def test_dispatch_pending_events_direct(client, db):
    """直接调用调度器也能投递待发闭环事件（不依赖 HTTP 入口）。"""
    _create_warning(client)
    _eval(client, NOMINAL_SAMPLE)

    rows = _resolved_outbox(db)
    assert len(rows) == 1
    event_dispatch.dispatch_pending_events(db)
    db.expire_all()
    assert _resolved_outbox(db)[0].status == OutboxStatus.SENT.value
