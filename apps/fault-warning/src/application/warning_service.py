"""B 的预警用例：查询、确认、接收维修结论闭环。

状态迁移与结论映射见 :mod:`src.domain.state_machine`。
每次状态或风险变化都会写一条 :class:`~src.domain.models.WarningStatusHistory`，
保证"预警如何被关闭/修正/标注"可回溯（``docs/06`` 第 10 节第 5 条）。
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.application.serializers import (
    event_accepted,
    serialize_warning,
    warning_page,
)
from src.domain import models
from src.domain.enums import (
    MaintenanceResult,
    RiskLevel,
    WarningAction,
    WarningStatus,
    escalate_risk,
)
from src.domain.errors import (
    VersionConflictError,
    WarningNotFoundError,
)
from src.domain.ids import parse_rfc3339, utc_now
from src.domain.state_machine import (
    TERMINAL_STATUSES,
    acknowledge_action,
    action_for_conclusion,
    transition_warning,
)
from src.infrastructure.idempotency import IdempotencyContext


def _as_utc(moment: datetime | None) -> datetime | None:
    """SQLite 会丢掉时区信息，读回的 naive 值按 UTC 处理。"""
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def get_warning(db: Session, warning_id: str) -> models.Warning:
    """按业务 ID 取预警；不存在抛 404 ``WARNING_NOT_FOUND``。"""
    warning = (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .first()
    )
    if warning is None:
        raise WarningNotFoundError(f"预警 {warning_id} 不存在")
    return warning


def record_history(
    db: Session,
    warning: models.Warning,
    *,
    action: str,
    from_status: str | None,
    to_status: str,
    operator_id: str | None = None,
    detail: str | None = None,
    trace_id: str | None = None,
) -> models.WarningStatusHistory:
    """写一条预警状态变更审计。"""
    entry = models.WarningStatusHistory(
        warning_pk=warning.id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        operator_id=operator_id,
        detail=str(detail)[:500] if detail is not None else None,
        trace_id=trace_id,
    )
    db.add(entry)
    return entry


def apply_transition(
    db: Session,
    warning: models.Warning,
    action: WarningAction,
    *,
    operator_id: str | None = None,
    detail: str | None = None,
    trace_id: str | None = None,
) -> WarningStatus:
    """执行一次合法状态迁移并记账（状态 + version + 审计）。

    非法迁移由 :func:`src.domain.state_machine.transition_warning` 抛 409。
    """
    current = WarningStatus(warning.status)
    target = transition_warning(current, action)

    record_history(
        db,
        warning,
        action=action.value,
        from_status=current.value,
        to_status=target.value,
        operator_id=operator_id,
        detail=detail,
        trace_id=trace_id,
    )
    warning.status = target.value
    warning.version += 1
    return target


def mark_linked_to_order(
    db: Session,
    warning: models.Warning,
    order_id: str,
    trace_id: str,
    detail: str | None = None,
) -> None:
    """C 接收预警并返回 ``orderId`` 后回填关联工单。

    已闭环的预警不再改动状态；已经是 ``LINKED_TO_ORDER`` 的只更新关联号。
    """
    current = WarningStatus(warning.status)
    if current in TERMINAL_STATUSES:
        return

    warning.linked_order_id = order_id

    if current in (WarningStatus.OPEN, WarningStatus.ACKNOWLEDGED):
        apply_transition(
            db,
            warning,
            WarningAction.LINK_TO_ORDER,
            operator_id="system",
            detail=detail or f"C 已建单 {order_id}",
            trace_id=trace_id,
        )


def list_warnings(
    db: Session,
    *,
    equipment_id: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """B-API-01：分页查询预警，按 ``warningAt`` 降序（``id`` 作稳定次序）。"""
    query = db.query(models.Warning)
    if equipment_id:
        query = query.filter(models.Warning.equipment_id == equipment_id)
    if risk_level:
        query = query.filter(models.Warning.risk_level == risk_level)
    if status:
        query = query.filter(models.Warning.status == status)

    total = query.count()
    items = (
        query.order_by(models.Warning.warning_at.desc(), models.Warning.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return warning_page(items, page, page_size, total)


def get_warning_detail(db: Session, warning_id: str) -> dict:
    """B-API-02：预警详情。"""
    return serialize_warning(get_warning(db, warning_id))


def acknowledge_warning(
    db: Session,
    warning_id: str,
    body: dict,
    trace_id: str,
    idem: IdempotencyContext | None = None,
) -> dict:
    """B-API-03：确认预警。

    仅 ``OPEN`` 可以确认（``OPEN -> ACKNOWLEDGED``）；
    已确认或已闭环的预警返回 409 ``INVALID_STATE_TRANSITION``。
    """
    warning = get_warning(db, warning_id)

    if body["expectedVersion"] != warning.version:
        raise VersionConflictError(
            f"版本冲突：期望 {body['expectedVersion']}，实际 {warning.version}"
        )

    previous = warning.status
    current = WarningStatus(previous)
    action = acknowledge_action(
        current, already_acknowledged=warning.acknowledged_at is not None
    )
    target = transition_warning(current, action)

    record_history(
        db,
        warning,
        action=action.value,
        from_status=previous,
        to_status=target.value,
        operator_id=body["operatorId"],
        detail=body.get("comment"),
        trace_id=trace_id,
    )
    warning.status = target.value
    warning.acknowledged_by = body["operatorId"]
    warning.acknowledged_at = utc_now()
    warning.version += 1

    result = serialize_warning(warning)
    if idem is not None:
        idem.remember(db, result, 200)
    db.commit()
    return result


def consume_maintenance_conclusion(
    db: Session,
    event: dict,
    trace_id: str,
    idem: IdempotencyContext | None = None,
) -> dict:
    """C-INT-05：接收维修结论并完成预警闭环。

    幂等与顺序规则（``docs/06`` 第 9 节）
    ------------------------------------
    * 以 ``eventId`` 去重，重复事件返回 ``duplicate=true``；
    * 同一 ``orderId`` 的结论按 ``completedAt`` 单调推进，
      迟到的旧结论只留档、不覆盖状态。
    """
    event_id = event["eventId"]
    payload = event["payload"]

    existing = (
        db.query(models.MaintenanceConclusion)
        .filter(models.MaintenanceConclusion.event_id == event_id)
        .first()
    )
    if existing is not None:
        result = event_accepted(trace_id, duplicate=True)
        if idem is not None:
            idem.remember(db, result, 202)
        db.commit()
        return result

    order_id = payload["orderId"]
    completed_at = parse_rfc3339(payload["completedAt"])

    latest = (
        db.query(models.MaintenanceConclusion)
        .filter(models.MaintenanceConclusion.order_id == order_id)
        .order_by(models.MaintenanceConclusion.completed_at.desc())
        .first()
    )
    is_stale = (
        latest is not None
        and _as_utc(latest.completed_at) >= completed_at
    )

    # 未知 warningId 必须在落库之前判 404，避免留下无法解释的结论记录
    warning = None
    if payload["warningId"]:
        warning = get_warning(db, payload["warningId"])

    db.add(
        models.MaintenanceConclusion(
            event_id=event_id,
            order_id=order_id,
            warning_id=payload["warningId"],
            equipment_id=payload["equipmentId"],
            root_cause=payload["rootCause"],
            measures=payload["measures"],
            result=payload["result"].value,
            effective=payload["effective"],
            completed_at=completed_at,
            submitted_by=payload["submittedBy"],
            downtime_minutes=payload["downtimeMinutes"],
            trace_id=trace_id,
        )
    )

    if warning is not None and not is_stale:
        _apply_conclusion(db, warning, payload, trace_id)

    result = event_accepted(trace_id, duplicate=False)
    if idem is not None:
        idem.remember(db, result, 202)
    db.commit()
    return result


def _apply_conclusion(
    db: Session, warning: models.Warning, payload: dict, trace_id: str
) -> None:
    """按维修结论推进预警状态或升级风险。"""
    current = WarningStatus(warning.status)
    if current in TERMINAL_STATUSES:
        # 已闭环：结论只作留档，不反向改写状态
        return

    result: MaintenanceResult = payload["result"]
    submitted_by = payload["submittedBy"]

    if result is MaintenanceResult.NOT_RECOVERED:
        # 状态保持打开，允许升级风险（docs/06 第 10 节第 5 条）
        escalated = escalate_risk(RiskLevel(warning.risk_level))
        if escalated.value != warning.risk_level:
            warning.risk_level = escalated.value
            warning.version += 1
            record_history(
                db,
                warning,
                action="ESCALATE_RISK",
                from_status=current.value,
                to_status=current.value,
                operator_id=submitted_by,
                detail=(
                    f"维修未恢复（{payload['orderId']}），"
                    f"风险升级为 {escalated.value}"
                ),
                trace_id=trace_id,
            )
        return

    action = action_for_conclusion(result, bool(payload["effective"]))
    if action is None:  # pragma: no cover - 枚举已穷尽，防御性分支
        return

    target = transition_warning(current, action)
    record_history(
        db,
        warning,
        action=action.value,
        from_status=current.value,
        to_status=target.value,
        operator_id=submitted_by,
        detail=(
            f"{result.value} / effective={payload['effective']} / "
            f"order={payload['orderId']}"
        ),
        trace_id=trace_id,
    )
    warning.status = target.value
    warning.version += 1
