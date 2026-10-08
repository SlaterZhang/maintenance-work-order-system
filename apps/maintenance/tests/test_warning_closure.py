"""C-INT-09：预警自动闭环通知 → 结掉悬空的早期工单（2026-10-07 新增）。

背景
----
现场：设备已"恢复正常数据"（EQ-000001 运行中），但 B 侧预警
``WARN-20261007-0001`` 悬在 ``LINKED_TO_ORDER``，C 侧工单
``WO-20261007-0995`` 永远停在 ``PENDING_CONFIRMATION``——
"恢复正常数据"绕过 C 的工单流程，B 收不到维修结论（C-INT-05）。

B 现在会在恢复评估（LOW）时自动闭环预警并发本事件；C 据此
**只结掉从未进入维修的早期工单**，已进入维修/已完成的工单保持不动
（用户 2026-10-07 决策）。
"""
import uuid

import pytest

from tests.conftest import INTERNAL_TOKEN, warning_event_payload

URL = "/api/v1/integration/warning-closures"

USER_HEADERS = {
    "Authorization": "Bearer test-token-USER-C-001",
    "X-Trace-Id": "trace-wo-0001",
}

HEADERS = {
    "X-Internal-Token": INTERNAL_TOKEN,
    "X-Trace-Id": "trace-test-0001",
    "Content-Type": "application/json",
}


def _headers(idem=None):
    h = dict(HEADERS)
    h["Idempotency-Key"] = idem or str(uuid.uuid4())
    return h


def _closure_event(warning_id="WARN-20260917-0001", **overrides) -> dict:
    """契约 ``WarningResolvedEvent``（C-INT-09）。"""
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": "WarningResolvedReported",
        "schemaVersion": "2.0",
        "occurredAt": "2026-10-07T13:30:00Z",
        "sourceMember": "MEMBER_B",
        "traceId": "trace-test-0001",
        "payload": {
            "warningId": warning_id,
            "equipmentId": "EQ-000001",
            "healthScore": 94.7,
            "resolvedAt": "2026-10-07T13:29:55Z",
            "resolvedBy": "USER-SYSTEM-AUTO",
            "reason": "设备遥测恢复正常（健康评估 LOW），预警自动闭环",
            "linkedOrderId": None,
        },
    }
    payload_overrides = overrides.pop("payload", None)
    if payload_overrides:
        event["payload"].update(payload_overrides)
    event.update(overrides)
    return event


def _create_order_via_warning(client, warning_id="WARN-20260917-0001") -> str:
    """C-INT-03 建单：高风险预警 → PENDING_CONFIRMATION 工单。"""
    r = client.post(
        "/api/v1/integration/warning-events",
        json=warning_event_payload(warning_id=warning_id, risk="CRITICAL"),
        headers=_headers(),
    )
    assert r.status_code == 202, r.text
    return r.json()["orderId"]


def _post_closure(client, event, idem=None):
    return client.post(URL, json=event, headers=_headers(idem))


def _cmd(client, order_id, action, expected_version=0, **extra):
    body = {"action": action, "operatorId": "USER-C-001",
            "expectedVersion": expected_version, **extra}
    return client.post(
        f"/api/v1/work-orders/{order_id}/commands",
        json=body,
        headers={**USER_HEADERS,
                 "Idempotency-Key": f"k-{order_id}-{action}-{expected_version}"},
    )


def _order(db, order_id):
    from src.domain import models
    db.expire_all()
    return db.query(models.WorkOrder).filter(
        models.WorkOrder.order_id == order_id).one()


# ---------- 早期工单自动结单 ----------
def test_pending_confirmation_order_is_auto_cancelled(
        client, db, mock_equipment, captured_cancellations):
    """用户场景回归：预警闭环后，待确认工单必须自动结单并回流 B。"""
    order_id = _create_order_via_warning(client)
    order = _order(db, order_id)
    assert order.status == "PENDING_CONFIRMATION"
    version_before = order.version

    response = _post_closure(client, _closure_event())
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["accepted"] is True
    assert data["duplicate"] is False
    assert data["orderId"] == order_id
    assert data["action"] == "AUTO_CANCELLED"

    after = _order(db, order_id)
    assert after.status == "CANCELLED"
    assert after.version == version_before + 1

    # 回流 B 的 OrderCancelledReported（C-INT-08）也要发出
    assert len(captured_cancellations) == 1
    event = captured_cancellations[0]
    assert event["orderId"] == order_id
    assert event["warningId"] == "WARN-20260917-0001"
    assert event["cancelledBy"] == "USER-SYSTEM-AUTO"
    assert "自动结单" in (event["reason"] or "")


@pytest.mark.parametrize("target_status", ["PENDING_ASSIGNMENT", "PENDING_ACCEPTANCE"])
def test_auto_cancel_covers_all_pre_maintenance_states(
        client, db, mock_equipment, captured_cancellations, target_status):
    """状态机 CANCEL 允许的早三态都应支持自动结单。"""
    order_id = _create_order_via_warning(client, warning_id="WARN-20260917-7777")
    if target_status == "PENDING_ASSIGNMENT":
        assert _cmd(client, order_id, "CONFIRM").status_code == 200
    else:
        assert _cmd(client, order_id, "CONFIRM").status_code == 200
        assert _cmd(client, order_id, "ASSIGN", assigneeId="USER-C-002",
                    expected_version=1).status_code == 200
    assert _order(db, order_id).status == target_status

    response = _post_closure(
        client, _closure_event(warning_id="WARN-20260917-7777"))
    assert response.status_code == 202, response.text
    assert response.json()["action"] == "AUTO_CANCELLED"
    assert _order(db, order_id).status == "CANCELLED"
    assert len(captured_cancellations) == 1


def test_auto_cancel_writes_audit_trail(client, db, mock_equipment,
                                        captured_cancellations):
    order_id = _create_order_via_warning(client)
    _post_closure(client, _closure_event())

    from src.domain import models
    db.expire_all()
    pk = _order(db, order_id).id  # 审计表的 order_id 是主键外键，不是业务单号
    db.expire_all()
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.order_id == pk,
        models.AuditLog.action == "AUTO_CLOSE_ON_WARNING_RESOLVED",
    ).all()
    assert logs, "自动结单必须留下审计记录"
    assert logs[-1].before_value == "PENDING_CONFIRMATION"
    assert logs[-1].after_value == "CANCELLED"
    assert logs[-1].operator_id == "USER-SYSTEM-AUTO"


# ---------- 已进入维修的工单不动 ----------
def test_maintaining_order_is_not_auto_cancelled(
        client, db, mock_equipment, captured_cancellations):
    """已进入维修的工单不能自动结单（状态机也不允许 CANCEL）。"""
    order_id = _create_order_via_warning(client)
    assert _cmd(client, order_id, "CONFIRM").status_code == 200
    assert _cmd(client, order_id, "ASSIGN", assigneeId="USER-C-002",
                expected_version=1).status_code == 200
    assert _cmd(client, order_id, "ACCEPT", expected_version=2).status_code == 200
    assert _cmd(client, order_id, "START", expected_version=3).status_code == 200
    assert _order(db, order_id).status == "MAINTAINING"
    version_before = _order(db, order_id).version

    response = _post_closure(client, _closure_event())
    assert response.status_code == 202, response.text
    assert response.json()["action"] == "SKIPPED_MAINTAINING"

    after = _order(db, order_id)
    assert after.status == "MAINTAINING"
    assert after.version == version_before, "被跳过的工单不得推进版本"
    assert captured_cancellations == [], "未结单就不该回流取消事件"


def test_completed_order_is_not_touched(client, db, mock_equipment,
                                        captured_cancellations, captured_conclusions):
    """已完成的工单保持不动（用户口径：完成了就不用操作工单）。"""
    order_id = _create_order_via_warning(client)
    assert _cmd(client, order_id, "CONFIRM").status_code == 200
    assert _cmd(client, order_id, "ASSIGN", assigneeId="USER-C-002",
                expected_version=1).status_code == 200
    assert _cmd(client, order_id, "ACCEPT", expected_version=2).status_code == 200
    assert _cmd(client, order_id, "START", expected_version=3).status_code == 200
    assert _cmd(
        client, order_id, "SUBMIT_FOR_INSPECTION",
        expected_version=4,
        conclusion={"rootCause": "轴承磨损", "measures": "已更换",
                    "result": "RECOVERED", "effective": True,
                    "completedAt": "2026-10-07T14:00:00Z",
                    "downtimeMinutes": 60},
    ).status_code == 200
    assert _cmd(client, order_id, "PASS_INSPECTION",
                expected_version=5).status_code == 200
    assert _order(db, order_id).status == "COMPLETED"
    version_before = _order(db, order_id).version

    response = _post_closure(client, _closure_event())
    assert response.status_code == 202, response.text
    assert response.json()["action"] == "SKIPPED_COMPLETED"
    assert _order(db, order_id).version == version_before
    assert captured_cancellations == []


def test_closure_without_related_order_is_noop(client, db, mock_equipment):
    response = _post_closure(client, _closure_event(warning_id="WARN-19990101-0001"))
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["action"] == "NO_ORDER"
    assert data["orderId"] is None


# ---------- 幂等 ----------
def test_same_event_id_replays(client, db, mock_equipment, captured_cancellations):
    order_id = _create_order_via_warning(client)
    event = _closure_event()
    key = str(uuid.uuid4())

    first = _post_closure(client, event, idem=key)
    second = _post_closure(client, event, idem=key)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["action"] == "AUTO_CANCELLED"
    assert first.json()["duplicate"] is False
    # 第二条同 eventId：服务层事件去重命中，回报放但不再动作
    assert second.json()["duplicate"] is True
    assert second.json()["action"] == "REPLAYED"
    assert second.json()["orderId"] == order_id

    order = _order(db, order_id)
    assert order.status == "CANCELLED"
    assert len(captured_cancellations) == 1, "幂等回放不得重复回流"


def test_different_event_id_for_same_warning_is_archived(
        client, db, mock_equipment, captured_cancellations):
    """同一预警的第二条闭环事件：工单已取消，不再重复动作。"""
    order_id = _create_order_via_warning(client)
    first = _post_closure(client, _closure_event())
    assert first.json()["action"] == "AUTO_CANCELLED"

    second = _post_closure(client, _closure_event())
    assert second.status_code == 202, second.text
    assert second.json()["action"] == "SKIPPED_CANCELLED"
    assert len(captured_cancellations) == 1


# ---------- 校验与鉴权 ----------
def test_missing_internal_token_401(client):
    r = client.post(URL, json=_closure_event(), headers={
        "X-Trace-Id": "trace-x",
        "Idempotency-Key": str(uuid.uuid4()),
    })
    assert r.status_code == 401


def test_missing_warning_id_400(client, mock_equipment):
    event = _closure_event(payload={"warningId": None})
    r = _post_closure(client, event)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "BAD_REQUEST"


def test_missing_event_id_400(client, mock_equipment):
    event = _closure_event(eventId=None)
    r = _post_closure(client, event)
    assert r.status_code == 400, r.text
