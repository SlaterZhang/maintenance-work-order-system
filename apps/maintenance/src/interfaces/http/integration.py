from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from src.infrastructure.db import get_db
from src.application import work_order_service
from src.interfaces.http.deps import trace_id as get_trace_id
from src.interfaces.http.deps import internal_token

router = APIRouter(prefix="/api/v1/integration", tags=["C-集成入口"])


@router.post("/warning-events", status_code=202)
def consume_warning_raised(
    body: dict,
    x_trace_id: str = Depends(get_trace_id),
    _token: str = Depends(internal_token),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """
    C-INT-03：接收成员B的 WarningRaised 事件
    - 202：已接收（含 duplicate）
    - 422：LOW/MEDIUM 不满足自动建单
    """
    return work_order_service.ingest_warning_event(db, body, x_trace_id)