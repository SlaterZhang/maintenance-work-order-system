from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from src.application import warning_service
from src.domain.errors import BadRequestError, IdempotencyKeyMismatchError
from src.infrastructure.db import get_db
from src.interfaces.http.deps import internal_token, trace_id

router = APIRouter(prefix="/api/v1/integration", tags=["C-INT-05 维修结论"])


@router.post("/maintenance-conclusions", status_code=202)
def consume_maintenance_conclusion(
    body: dict,
    x_trace_id: str = Depends(trace_id),
    _token: str = Depends(internal_token),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise BadRequestError("缺少 Idempotency-Key")
    if idempotency_key != body.get("eventId"):
        raise IdempotencyKeyMismatchError()
    return warning_service.receive_conclusion(db, body, x_trace_id)
