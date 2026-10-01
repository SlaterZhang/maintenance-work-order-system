"""outbox 事件的投递与回填。

分工
----
* :mod:`src.infrastructure.outbox` 只负责状态记账（PENDING / SENT / FAILED）；
* 本模块负责"这条事件到底怎么发、发完要做什么"。

``WarningRaised`` 投递成功后，用 C 返回的 ``orderId`` 回填
``Warning.linkedOrderId`` 并把状态推进到 ``LINKED_TO_ORDER``。
"""

from sqlalchemy.orm import Session

from src.application import warning_service
from src.domain import models
from src.domain.enums import OutboxEventType
from src.infrastructure import outbox
from src.interfaces.clients import member_c, member_d


def deliver_event(
    db: Session, row: models.OutboxEvent, payload: dict
) -> tuple[bool, str | None]:
    """按事件类型投递一条 outbox 记录。"""
    if row.event_type == OutboxEventType.WARNING_RAISED.value:
        return _deliver_warning_raised(db, row, payload)
    if row.event_type == OutboxEventType.WARNING_NOTIFICATION.value:
        return _deliver_notification(row, payload)
    return False, f"未知事件类型：{row.event_type}"


def dispatch_pending_events(db: Session, limit: int = 20) -> dict:
    """尝试投递所有待发送事件；返回投递统计。

    :mod:`src.infrastructure.outbox` 约定的 handler 签名是 ``(row, payload)``，
    而这里需要会话，因此用闭包把 ``db`` 绑进去。
    """

    def handler(row: models.OutboxEvent, payload: dict):
        return deliver_event(db, row, payload)

    return outbox.dispatch_pending(db, handler, limit=limit)


def _deliver_warning_raised(
    db: Session, row: models.OutboxEvent, event: dict
) -> tuple[bool, str | None]:
    trace_id = row.trace_id or event.get("traceId") or "trace-unknown"
    ok, response, error = member_c.send_warning_raised(
        event, trace_id, row.event_id
    )
    if not ok:
        return False, error

    order_id = (response or {}).get("orderId")
    warning_id = (event.get("payload") or {}).get("warningId")
    if order_id and warning_id:
        warning = (
            db.query(models.Warning)
            .filter(models.Warning.warning_id == warning_id)
            .first()
        )
        if warning is not None:
            warning_service.mark_linked_to_order(
                db,
                warning,
                order_id,
                trace_id,
                detail="C 已接收预警并建立工单",
            )
            db.commit()
    return True, None


def _deliver_notification(
    row: models.OutboxEvent, body: dict
) -> tuple[bool, str | None]:
    return member_d.submit_notification(
        recipients=list(body.get("recipientUserIds") or []),
        template_code=body.get("templateCode", ""),
        variables=dict(body.get("variables") or {}),
        trace_id=row.trace_id or "trace-unknown",
        idempotency_key=row.event_id,
    )
