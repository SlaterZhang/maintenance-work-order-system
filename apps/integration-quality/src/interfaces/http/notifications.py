from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.application import identity_service
from src.domain.errors import BadRequestError
from src.infrastructure.db import get_db
from src.interfaces.http.deps import idempotency_key, internal_token, trace_id

router = APIRouter(prefix="/api/v1", tags=["C-INT-07 通知任务"])


@router.post("/notifications", status_code=202)
def submit_notification(
    body: dict,
    x_trace_id: str = Depends(trace_id),
    _token: str = Depends(internal_token),
    idem_key: str | None = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    if not idem_key:
        raise BadRequestError("缺少 Idempotency-Key")
    return identity_service.submit_notification(db, body, idem_key, x_trace_id)
