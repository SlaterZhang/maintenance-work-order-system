"""C-INT-05：接收成员 C 的维修结论；C-INT-08：接收成员 C 的工单取消。

契约：``x-owner-member: MEMBER_B``、``security: internalToken``、成功 202。
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.application import warning_service
from src.infrastructure.db import get_db
from src.infrastructure.idempotency import IdempotencyContext
from src.interfaces.http.deps import (
    idempotency_key,
    internal_token,
    required_trace_id,
)
from src.interfaces.http.payloads import (
    parse_maintenance_conclusion_event,
    parse_order_cancellation_event,
)

router = APIRouter(prefix="/api/v1/integration", tags=["B-集成入口"])


@router.post("/maintenance-conclusions", status_code=202)
def consume_maintenance_conclusion(
    body: dict,
    x_trace_id: str = Depends(required_trace_id),
    _token: str = Depends(internal_token),
    idem_key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    """接收维修结论并推进预警闭环；``eventId`` 去重，重复返回 ``duplicate=true``。"""
    event = parse_maintenance_conclusion_event(body)
    idem = IdempotencyContext(key=idem_key, raw_body=body)

    cached = idem.replay(db)
    if cached is not None:
        return JSONResponse(status_code=cached.http_status, content=cached.body)

    return warning_service.consume_maintenance_conclusion(
        db, event, x_trace_id, idem=idem
    )


@router.post("/order-cancellations", status_code=202)
def consume_order_cancellation(
    body: dict,
    x_trace_id: str = Depends(required_trace_id),
    _token: str = Depends(internal_token),
    idem_key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    """C-INT-08：接收工单取消事件，关联预警闭环为 CANCELLED。

    ``Idempotency-Key``（= eventId）重复投递回放原响应；
    终态预警只留档不反向改写。
    """
    event = parse_order_cancellation_event(body)
    idem = IdempotencyContext(key=idem_key, raw_body=body)

    cached = idem.replay(db)
    if cached is not None:
        return JSONResponse(status_code=cached.http_status, content=cached.body)

    return warning_service.consume_order_cancellation(
        db, event, x_trace_id, idem=idem
    )
