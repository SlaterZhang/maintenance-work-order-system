from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.domain import models
from src.domain.enums import (
    WorkOrderStatus, WorkOrderAction, WorkOrderSource,
    WorkOrderPriority, RiskLevel,
)
from src.domain.errors import (
    WorkOrderNotFoundError, InvalidTransitionError, ConflictError,
)
from src.domain.state_machine import (
    transition_work_order, ACTION_PERMISSION,
)
from src.domain.rules import calc_due_at, map_priority, can_auto_create_order
from src.domain.ids import new_order_id
from src.interfaces.clients.member_a import MemberAClient
from src.interfaces.clients.member_b import MemberBClient


def _get_order(db: Session, order_id: str) -> models.WorkOrder:
    o = db.query(models.WorkOrder).filter(
        models.WorkOrder.order_id == order_id
    ).first()
    if not o:
        raise WorkOrderNotFoundError()
    return o


def _audit(db: Session, order: models.WorkOrder | None, action: str,
           operator: str, before=None, after=None, detail=None,
           trace_id=None):
    db.add(models.AuditLog(
        order_id=order.id if order else None,
        action=action, operator_id=operator,
        before_value=str(before) if before is not None else None,
        after_value=str(after) if after is not None else None,
        detail=detail, trace_id=trace_id,
    ))


# ---------- C-INT-03：接收预警事件 ----------
def ingest_warning_event(db: Session, event: dict,
                         trace_id: str) -> dict:
    """
    接收成员B的 WarningRaised 事件。
    - EventId 幂等
    - LOW/MEDIUM 返回 422
    - WarningId 已存在 -> 返回原 OrderId + duplicate=true
    - HIGH/CRITICAL -> 自动建 PENDING_CONFIRMATION 工单
    """
    payload = event["payload"]
    warning_id = payload["warningId"]
    equipment_id = payload["equipmentId"]
    risk = RiskLevel(payload["riskLevel"])

    # 幂等：EventId
    existed_event = db.query(models.ProcessedEvent).filter(
        models.ProcessedEvent.event_id == event["eventId"]
    ).first()
    if existed_event:
        return {
            "accepted": True, "duplicate": True,
            "orderId": existed_event.result_ref, "traceId": trace_id,
        }

    # 风险等级校验
    if not can_auto_create_order(risk):
        from src.domain.errors import LowRiskNotAcceptedError
        raise LowRiskNotAcceptedError()

    # WarningId 已建单 -> 直接返回原工单
    existed_order = db.query(models.WorkOrder).filter(
        models.WorkOrder.warning_id == warning_id
    ).first()
    if existed_order:
        db.add(models.ProcessedEvent(
            event_id=event["eventId"], event_type="WarningRaised",
            result_ref=existed_order.order_id, trace_id=trace_id,
        ))
        db.commit()
        return {
            "accepted": True, "duplicate": True,
            "orderId": existed_order.order_id, "traceId": trace_id,
        }

    # C-INT-01：查设备（必须成功，否则拒绝建单）
    equipment = MemberAClient.get_equipment(equipment_id, trace_id)
    if not equipment:
        from src.domain.errors import EquipmentNotFoundError
        raise EquipmentNotFoundError()

    order = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource.WARNING.value,
        warning_id=warning_id,
        equipment_id=equipment_id,
        equipment_name_snapshot=equipment["name"],
        title=f"预警自动建单：{payload['suspectedFault']}",
        description=payload["recommendedAction"],
        priority=map_priority(risk).value,
        status=WorkOrderStatus.PENDING_CONFIRMATION.value,
        reporter_id="system",
        due_at=calc_due_at(risk, datetime.fromisoformat(
            payload["warningAt"].replace("Z", "+00:00"))),
    )
    db.add(order)
    db.flush()

    db.add(models.ProcessedEvent(
        event_id=event["eventId"], event_type="WarningRaised",
        result_ref=order.order_id, trace_id=trace_id,
    ))
    _audit(db, order, "AUTO_CREATE_FROM_WARNING", "system",
           detail=f"warningId={warning_id}, risk={risk.value}",
           trace_id=trace_id)
    db.commit()

    return {
        "accepted": True, "duplicate": False,
        "orderId": order.order_id, "traceId": trace_id,
    }


# ---------- C-API-02：人工报修 ----------
def create_manual_order(db: Session, body: dict, trace_id: str) -> dict:
    equipment = MemberAClient.get_equipment(body["equipmentId"], trace_id)
    if not equipment:
        from src.domain.errors import EquipmentNotFoundError
        raise EquipmentNotFoundError()

    order = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource(body["sourceType"]).value,
        warning_id=None,
        equipment_id=body["equipmentId"],
        equipment_name_snapshot=equipment["name"],
        title=body["title"],
        description=body["description"],
        priority=WorkOrderPriority(body["priority"]).value,
        status=WorkOrderStatus.PENDING_CONFIRMATION.value,
        reporter_id=body["reporterId"],
        due_at=body.get("dueAt"),
    )
    db.add(order)
    db.flush()
    _audit(db, order, "CREATE_MANUAL", body["reporterId"], trace_id=trace_id)
    db.commit()
    return _serialize(order)


# ---------- C-API-04：执行工单命令 ----------
def execute_command(db: Session, order_id: str, body: dict,
                    trace_id: str, operator_permissions: list[str]) -> dict:
    order = _get_order(db, order_id)

    # 乐观锁
    if body["expectedVersion"] != order.version:
        raise ConflictError(
            f"版本冲突：期望 {body['expectedVersion']} 实际 {order.version}"
        )

    action = WorkOrderAction(body["action"])
    perm = ACTION_PERMISSION[action]
    if perm not in operator_permissions and "ADMIN_ALL" not in operator_permissions:
        from src.domain.errors import ForbiddenError
        raise ForbiddenError(f"缺少权限 {perm}")

    before = order.status
    target = transition_work_order(WorkOrderStatus(before), action)
    order.status = target.value

    # action 特有逻辑
    if action == WorkOrderAction.ASSIGN:
        if not body.get("assigneeId"):
            from src.domain.errors import BadRequestError
            raise BadRequestError("ASSIGN 必须提供 assigneeId")
        db.add(models.AssignmentHistory(
            order_id=order.id, from_user=order.assignee_id,
            to_user=body["assigneeId"], operator_id=body["operatorId"],
            comment=body.get("comment"),
        ))
        order.assignee_id = body["assigneeId"]

    elif action == WorkOrderAction.SUBMIT_FOR_INSPECTION:
        c = body.get("conclusion")
        if not c:
            from src.domain.errors import BadRequestError
            raise BadRequestError("SUBMIT_FOR_INSPECTION 必须提供 conclusion")
        order.root_cause = c["rootCause"]
        order.measures = c["measures"]
        order.maintenance_result = c["result"]
        order.effective = c["effective"]
        completed_raw = c["completedAt"]
        if isinstance(completed_raw, str):
            completed_raw = datetime.fromisoformat(
                completed_raw.replace("Z", "+00:00"))
        order.completed_at = completed_raw
        order.downtime_minutes = c.get("downtimeMinutes")
        order.concluded_by = body["operatorId"]

    elif action == WorkOrderAction.START:
        # C-INT-04：通知成员A 设备进入 MAINTAINING
        MemberAClient.notify_equipment_status(
            order_id=order.order_id,
            equipment_id=order.equipment_id,
            target_status="MAINTAINING",
            operator_id=body["operatorId"],
            reason="工程师开始维修",
            trace_id=trace_id,
        )
    elif action == WorkOrderAction.WAIT_FOR_PARTS:
        MemberAClient.notify_equipment_status(
            order_id=order.order_id,
            equipment_id=order.equipment_id,
            target_status="STOPPED",
            operator_id=body["operatorId"],
            reason="等待备件",
            trace_id=trace_id,
        )
    elif action == WorkOrderAction.PASS_INSPECTION:
        # 归档 + 通知 A 恢复运行 + 通知 B 维修结论
        MemberAClient.notify_equipment_status(
            order_id=order.order_id,
            equipment_id=order.equipment_id,
            target_status="RUNNING",
            operator_id=body["operatorId"],
            reason="验收通过，设备恢复运行",
            trace_id=trace_id,
        )
        if order.warning_id:
            MemberBClient.send_conclusion(
                order_id=order.order_id,
                warning_id=order.warning_id,
                equipment_id=order.equipment_id,
                root_cause=order.root_cause or "",
                measures=order.measures or "",
                result=order.maintenance_result or "RECOVERED",
                completed_at=order.completed_at or datetime.now(timezone.utc),
                effective=order.effective if order.effective is not None else True,
                submitted_by=body["operatorId"],
                trace_id=trace_id,
            )

    order.version += 1
    _audit(db, order, f"COMMAND:{action.value}", body["operatorId"],
           before=before, after=order.status, detail=body.get("comment"),
           trace_id=trace_id)
    db.commit()
    return _serialize(order)


# ---------- 序列化 ----------
def _serialize(o: models.WorkOrder) -> dict:
    conclusion = None
    if o.root_cause:
        conclusion = {
            "rootCause": o.root_cause,
            "measures": o.measures,
            "result": o.maintenance_result,
            "effective": o.effective,
            "completedAt": o.completed_at.isoformat() if o.completed_at else None,
            "downtimeMinutes": o.downtime_minutes,
            "submittedBy": o.concluded_by,
        }
    return {
        "orderId": o.order_id,
        "sourceType": o.source_type,
        "warningId": o.warning_id,
        "equipmentId": o.equipment_id,
        "equipmentNameSnapshot": o.equipment_name_snapshot,
        "title": o.title,
        "description": o.description,
        "priority": o.priority,
        "status": o.status,
        "reporterId": o.reporter_id,
        "assigneeId": o.assignee_id,
        "dueAt": o.due_at.isoformat() if o.due_at else None,
        "conclusion": conclusion,
        "version": o.version,
        "createdAt": o.created_at.isoformat(),
        "updatedAt": o.updated_at.isoformat(),
    }


def serialize_order(o: models.WorkOrder) -> dict:
    return _serialize(o)


def get_order(db: Session, order_id: str) -> models.WorkOrder:
    return _get_order(db, order_id)