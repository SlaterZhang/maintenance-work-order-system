"""outbox 待发送队列。

模式：**先提交业务状态，再投递事件**。

1. 用例在业务事务里调用 :func:`enqueue`，把事件写入 ``outbox_event``；
2. 与业务数据一起 ``commit``，此时"待发送"已经持久化，断电也不丢；
3. 然后调用 :func:`dispatch_pending` 尝试投递；
4. 投递成功置 ``SENT``，失败累加 ``attempts``；达到上限置 ``FAILED``，
   未达上限保持 ``PENDING``，下次可继续重试。

投递失败**不会**回滚已成立的业务事实，符合 ``docs/06`` 第 10 节第 7 条。

本模块只负责状态记账；"怎么发、发完要做什么"由调用方通过 ``handler`` 注入，
因此可以用假 handler 在没有网络的情况下测试整条链路。
"""

import json
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy.orm import Session

from src.config import settings
from src.domain.enums import OutboxEventType, OutboxStatus
from src.domain.ids import utc_now
from src.domain.models import OutboxEvent

# handler(event_row, payload_dict) -> (是否成功, 失败原因)
OutboxHandler = Callable[[OutboxEvent, dict], "tuple[bool, str | None]"]


def enqueue(
    db: Session,
    *,
    event_id: str,
    event_type: OutboxEventType,
    target_url: str,
    payload: dict,
    trace_id: str | None = None,
) -> OutboxEvent:
    """登记一条待发送事件。**不提交**，由调用方与业务写入同事务提交。"""
    row = OutboxEvent(
        event_id=event_id,
        event_type=event_type.value,
        target_url=target_url,
        payload=json.dumps(payload, ensure_ascii=False, default=str),
        status=OutboxStatus.PENDING.value,
        attempts=0,
        trace_id=trace_id,
    )
    db.add(row)
    return row


def pending_events(db: Session, limit: int = 20) -> list[OutboxEvent]:
    """按登记顺序返回待发送事件。"""
    return (
        db.query(OutboxEvent)
        .filter(OutboxEvent.status == OutboxStatus.PENDING.value)
        .order_by(OutboxEvent.id)
        .limit(limit)
        .all()
    )


def dispatch_pending(
    db: Session,
    handler: OutboxHandler,
    *,
    limit: int = 20,
    max_attempts: int | None = None,
) -> dict:
    """尝试投递所有 ``PENDING`` 事件。

    :returns: ``{"attempted", "sent", "failed", "exhausted"}``
    """
    budget = settings.event_max_retries if max_attempts is None else max_attempts
    summary = {"attempted": 0, "sent": 0, "failed": 0, "exhausted": 0}

    for row in pending_events(db, limit=limit):
        summary["attempted"] += 1
        payload = json.loads(row.payload)
        row.attempts += 1

        try:
            ok, error = handler(row, payload)
        except Exception as exc:  # noqa: BLE001 - outbox 必须吞掉任何投递异常
            ok, error = False, f"{type(exc).__name__}: {exc}"

        if ok:
            row.status = OutboxStatus.SENT.value
            row.last_error = None
            summary["sent"] += 1
        else:
            row.last_error = (error or "未知投递错误")[:500]
            if row.attempts >= budget:
                row.status = OutboxStatus.FAILED.value
                summary["exhausted"] += 1
            else:
                # 保持 PENDING，下次重试
                row.updated_at = utc_now()
                summary["failed"] += 1

    db.commit()
    return summary


def retry_backoff(attempts: int, base_seconds: float = 1.0) -> timedelta:
    """指数退避，供定时重试任务参考。"""
    return timedelta(seconds=base_seconds * (2 ** max(0, attempts - 1)))
