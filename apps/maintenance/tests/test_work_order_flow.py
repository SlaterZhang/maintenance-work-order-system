"""工单流程：人工报修 -> 确认 -> 派单 -> 接单 -> 开始 -> 提交验收 -> 通过"""
import pytest

from tests.conftest import INTERNAL_TOKEN


USER_HEADERS = {
    "Authorization": "Bearer test-token-USER-C-001",
    "X-Trace-Id": "trace-wo-0001",
}


def _cmd(client, order_id, action, operator="USER-C-001",
         expected_version=0, **extra):
    body = {"action": action, "operatorId": operator,
            "expectedVersion": expected_version, **extra}
    return client.post(
        f"/api/v1/work-orders/{order_id}/commands",
        json=body,
        headers={
            **USER_HEADERS,
            "Idempotency-Key": f"key-{order_id}-{action}-{expected_version}",
        },
    )


def _create_manual(client, equipment_id="EQ-000001"):
    body = {
        "sourceType": "MANUAL",
        "equipmentId": equipment_id,
        "title": "操作员报修",
        "description": "设备异响",
        "priority": "P3",
        "reporterId": "USER-C-001",
    }
    r = client.post(
        "/api/v1/work-orders", json=body,
        headers={
            **USER_HEADERS,
            "Idempotency-Key": f"create-{equipment_id}",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------- 创建 ----------
def test_create_manual_order(client, mock_equipment):
    o = _create_manual(client)
    assert o["orderId"].startswith("WO-")
    assert o["status"] == "PENDING_CONFIRMATION"
    assert o["version"] == 0
    assert o["equipmentNameSnapshot"]


def test_create_manual_order_missing_required_field_400(client, mock_equipment):
    """缺契约必填字段（曾 KeyError 落成 500，2026-10-07 回归）。"""
    body = {   # 缺 reporterId（前端曾漏传导致线上 500）
        "sourceType": "MANUAL", "equipmentId": "EQ-000001",
        "title": "操作员报修", "priority": "P3",
    }
    r = client.post(
        "/api/v1/work-orders", json=body,
        headers={**USER_HEADERS, "Idempotency-Key": "missing-reporter-1"},
    )
    assert r.status_code == 400, r.text
    payload = r.json()
    assert payload["code"] == "BAD_REQUEST"
    assert "reporterId" in payload["message"]


def test_create_manual_order_defaults_optional_fields(client, mock_equipment):
    """description/priority 缺省时有兜底，不再裸取键。"""
    body = {
        "sourceType": "MANUAL", "equipmentId": "EQ-000001",
        "title": "巡检发现异响", "reporterId": "USER-A-001",
    }
    r = client.post(
        "/api/v1/work-orders", json=body,
        headers={**USER_HEADERS, "Idempotency-Key": "defaults-optional-1"},
    )
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["description"] == "巡检发现异响"   # 缺省回落为标题
    assert o["priority"] == "P2"


def test_create_manual_order_idempotent(client, db, mock_equipment):
    body = {
        "sourceType": "MANUAL", "equipmentId": "EQ-000001",
        "title": "t", "description": "d",
        "priority": "P3", "reporterId": "USER-C-001",
    }
    headers = {
        **USER_HEADERS,
        "Idempotency-Key": "same-key-1111",
    }
    r1 = client.post("/api/v1/work-orders", json=body, headers=headers)
    r2 = client.post("/api/v1/work-orders", json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["orderId"] == r2.json()["orderId"]

    from src.domain import models
    assert db.query(models.WorkOrder).count() == 1


def test_idempotency_same_key_different_body_409(client, mock_equipment):
    headers = {**USER_HEADERS, "Idempotency-Key": "conflict-key"}
    body1 = {
        "sourceType": "MANUAL", "equipmentId": "EQ-000001",
        "title": "t1", "description": "d1",
        "priority": "P3", "reporterId": "USER-C-001",
    }
    body2 = dict(body1, title="t2")
    client.post("/api/v1/work-orders", json=body1, headers=headers)
    r = client.post("/api/v1/work-orders", json=body2, headers=headers)
    assert r.status_code == 409
    assert r.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"


# ---------- 完整正向流程 ----------
def test_full_happy_path(client, db, mock_equipment,
                         captured_status_events, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]

    r = _cmd(client, oid, "CONFIRM")
    assert r.status_code == 200
    assert r.json()["status"] == "PENDING_ASSIGNMENT"
    assert r.json()["version"] == 1

    r = _cmd(client, oid, "ASSIGN",
             expected_version=1, assigneeId="USER-C-ENG-1")
    assert r.json()["status"] == "PENDING_ACCEPTANCE"
    assert r.json()["assigneeId"] == "USER-C-ENG-1"

    r = _cmd(client, oid, "ACCEPT", expected_version=2)
    assert r.json()["status"] == "PENDING_MAINTENANCE"

    r = _cmd(client, oid, "START", expected_version=3)
    assert r.json()["status"] == "MAINTAINING"
    # C-INT-04：通知 A 设备进入 MAINTAINING
    assert any(e["targetStatus"] == "MAINTAINING"
               for e in captured_status_events)

    conclusion = {
        "rootCause": "轴承磨损",
        "measures": "更换轴承",
        "result": "RECOVERED",
        "effective": True,
        "completedAt": "2026-09-17T12:00:00Z",
    }
    r = _cmd(client, oid, "SUBMIT_FOR_INSPECTION",
             expected_version=4, conclusion=conclusion)
    assert r.json()["status"] == "PENDING_INSPECTION"
    assert r.json()["conclusion"]["rootCause"] == "轴承磨损"

    r = _cmd(client, oid, "PASS_INSPECTION", expected_version=5)
    assert r.json()["status"] == "COMPLETED"
    # C-INT-04：通知 A 设备恢复 RUNNING
    assert any(e["targetStatus"] == "RUNNING"
               for e in captured_status_events)


# ---------- 验收不通过返工 ----------
def test_reject_inspection_returns_to_maintaining(
        client, mock_equipment, captured_status_events, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    _cmd(client, oid, "CONFIRM")
    _cmd(client, oid, "ASSIGN", expected_version=1,
         assigneeId="USER-C-ENG-1")
    _cmd(client, oid, "ACCEPT", expected_version=2)
    _cmd(client, oid, "START", expected_version=3)
    _cmd(client, oid, "SUBMIT_FOR_INSPECTION", expected_version=4,
         conclusion={
             "rootCause": "x", "measures": "y", "result": "PARTIALLY_RECOVERED",
             "effective": False, "completedAt": "2026-09-17T12:00:00Z",
         })

    r = _cmd(client, oid, "REJECT_INSPECTION", expected_version=5,
             comment="试运行振动超标")
    assert r.json()["status"] == "MAINTAINING"


# ---------- 乐观锁 ----------
def test_optimistic_lock_conflict(client, mock_equipment, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    _cmd(client, oid, "CONFIRM")
    # 用错的 version
    r = _cmd(client, oid, "ASSIGN", expected_version=99,
             assigneeId="USER-C-ENG-1")
    assert r.status_code == 409
    assert r.json()["code"] == "CONFLICT"


# ---------- 非法状态迁移 ----------
def test_invalid_transition_409(client, mock_equipment, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    # 还没确认就 ACCEPT
    r = _cmd(client, oid, "ACCEPT")
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE_TRANSITION"


# ---------- 取消 ----------
def test_cancel_in_early_state(client, mock_equipment, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    r = _cmd(client, oid, "CANCEL", comment="重复报修")
    assert r.json()["status"] == "CANCELLED"


def test_cannot_cancel_after_start(client, mock_equipment,
                                    captured_status_events, mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    _cmd(client, oid, "CONFIRM")
    _cmd(client, oid, "ASSIGN", expected_version=1, assigneeId="ENG-1")
    _cmd(client, oid, "ACCEPT", expected_version=2)
    _cmd(client, oid, "START", expected_version=3)
    r = _cmd(client, oid, "CANCEL", expected_version=4)
    assert r.status_code == 409


# ---------- 缺少 assigneeId ----------
def test_assign_without_assignee_bad_request(client, mock_equipment,
                                              mock_permissions):
    o = _create_manual(client)
    oid = o["orderId"]
    _cmd(client, oid, "CONFIRM")
    r = _cmd(client, oid, "ASSIGN", expected_version=1)  # 不传 assigneeId
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


# ---------- 权限拒绝 ----------
def test_permission_denied(client, mock_equipment, monkeypatch):
    from src.interfaces.clients import member_d

    o = _create_manual(client)   # 先用默认全量权限建单
    oid = o["orderId"]

    def fake_verify(token, trace_id):
        return {
            "userId": "USER-C-001", "displayName": "无权限用户",
            "roleCodes": ["EQUIPMENT_OPERATOR"],
            "permissions": [], "organization": "x", "enabled": True,
        }

    monkeypatch.setattr(
        member_d.MemberDClient, "verify_bearer",
        staticmethod(fake_verify),
    )
    r = _cmd(client, oid, "CONFIRM")
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


def test_commands_reject_forged_identity_header(client, mock_equipment):
    """X-User-Id 头不再是身份来源：不带 Bearer 一律 401。"""
    o = _create_manual(client)
    oid = o["orderId"]
    r = client.post(
        f"/api/v1/work-orders/{oid}/commands",
        json={"action": "CONFIRM", "operatorId": "USER-C-001",
              "expectedVersion": 0},
        headers={"X-User-Id": "USER-C-001", "X-Trace-Id": "trace-x",
                 "Authorization": "Basic forged",   # 覆盖默认 Bearer
                 "Idempotency-Key": "key-forged-header-1"},
    )
    assert r.status_code == 401


def test_forged_operator_id_is_overridden(client, db, mock_equipment):
    """报文里的 operatorId 不能决定操作人：服务端以 JWT 身份覆写。"""
    o = _create_manual(client)
    oid = o["orderId"]
    r = _cmd(client, oid, "CONFIRM", operator="USER-D-001")
    assert r.status_code == 200, r.text
    from src.domain import models
    forged = db.query(models.AuditLog).filter(
        models.AuditLog.operator_id == "USER-D-001").count()
    confirmed = db.query(models.AuditLog).filter(
        models.AuditLog.action == "COMMAND:CONFIRM",
        models.AuditLog.operator_id == "USER-C-001").count()
    assert forged == 0, "伪造的 operatorId 不应出现在审计中"
    assert confirmed >= 1, "审计应记录令牌身份 USER-C-001"


# ---------- 查询 ----------
def test_list_filter_by_status(client, mock_equipment, mock_permissions):
    o1 = _create_manual(client, "EQ-000001")
    _create_manual(client, "EQ-000002")
    _cmd(client, o1["orderId"], "CONFIRM")
    r = client.get("/api/v1/work-orders?status=PENDING_CONFIRMATION",
                   headers=USER_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["equipmentId"] == "EQ-000002"


def test_get_order_detail(client, mock_equipment):
    o = _create_manual(client)
    r = client.get(f"/api/v1/work-orders/{o['orderId']}",
                   headers=USER_HEADERS)
    assert r.status_code == 200
    assert r.json()["orderId"] == o["orderId"]


def test_get_order_not_found(client):
    r = client.get("/api/v1/work-orders/WO-20260917-9999",
                   headers=USER_HEADERS)
    assert r.status_code == 404
    assert r.json()["code"] == "WORK_ORDER_NOT_FOUND"


# ---------- 维修结论回传 B ----------
def test_conclusion_sent_to_member_b(
        client, db, mock_equipment, captured_status_events,
        captured_conclusions, mock_permissions):
    from src.domain import models
    from src.domain.ids import new_order_id
    from src.domain.enums import (
        WorkOrderStatus, WorkOrderSource, WorkOrderPriority,
    )

    # 直接插一条带 warningId 的工单，验证闭环回传
    order = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource.WARNING.value,
        warning_id="WARN-20260917-8888",
        equipment_id="EQ-000001",
        equipment_name_snapshot="设备",
        title="t", description="d",
        priority=WorkOrderPriority.P1.value,
        status=WorkOrderStatus.PENDING_CONFIRMATION.value,
        reporter_id="system",
    )
    db.add(order)
    db.commit()
    oid = order.order_id

    _cmd(client, oid, "CONFIRM")
    _cmd(client, oid, "ASSIGN", expected_version=1, assigneeId="ENG-1")
    _cmd(client, oid, "ACCEPT", expected_version=2)
    _cmd(client, oid, "START", expected_version=3)
    _cmd(client, oid, "SUBMIT_FOR_INSPECTION", expected_version=4,
         conclusion={
             "rootCause": "轴承磨损", "measures": "更换",
             "result": "RECOVERED", "effective": True,
             "completedAt": "2026-09-17T12:00:00Z",
         })
    _cmd(client, oid, "PASS_INSPECTION", expected_version=5)

    assert len(captured_conclusions) == 1
    c = captured_conclusions[0]
    assert c["warningId"] == "WARN-20260917-8888"
    assert c["rootCause"] == "轴承磨损"
    assert c["result"] == "RECOVERED"


# ---------- 工单取消回传 B（C-INT-08，2026-10-07 新增） ----------
def test_cancel_notifies_member_b_when_warning_linked(
        client, db, mock_equipment, captured_cancellations, mock_permissions):
    """取消预警关联工单 → 必须发送 OrderCancelledReported 事件。"""
    from src.domain import models
    from src.domain.ids import new_order_id
    from src.domain.enums import (
        WorkOrderStatus, WorkOrderSource, WorkOrderPriority,
    )

    order = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource.WARNING.value,
        warning_id="WARN-20261007-0001",
        equipment_id="EQ-000001",
        equipment_name_snapshot="设备",
        title="t", description="d",
        priority=WorkOrderPriority.P1.value,
        status=WorkOrderStatus.PENDING_CONFIRMATION.value,
        reporter_id="system",
    )
    db.add(order)
    db.commit()
    oid = order.order_id

    resp = _cmd(client, oid, "CANCEL", comment="重复建单")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED"

    assert len(captured_cancellations) == 1
    event = captured_cancellations[0]
    assert event["orderId"] == oid
    assert event["warningId"] == "WARN-20261007-0001"
    assert event["cancelledBy"]
    assert event["reason"] == "重复建单"


def test_cancel_manual_order_skips_member_b_notification(
        client, db, mock_equipment, captured_cancellations, mock_permissions):
    """人工报修工单（无预警关联）取消 → 不发回流事件。"""
    o = _create_manual(client)  # warning_id = None
    resp = _cmd(client, o["orderId"], "CANCEL")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED"
    assert captured_cancellations == []