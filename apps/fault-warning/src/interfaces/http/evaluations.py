from fastapi import APIRouter, BackgroundTasks, Depends, Header
from sqlalchemy.orm import Session

from src.application import warning_client, warning_service
from src.domain.errors import IdempotencyKeyMismatchError
from src.infrastructure.db import get_db
from src.interfaces.http.deps import internal_token, trace_id

router = APIRouter(prefix="/api/v1", tags=["C-INT-02 健康评估"])


@router.post("/health-evaluations")
def evaluate_equipment_health(
    body: dict,
    background: BackgroundTasks,
    x_trace_id: str = Depends(trace_id),
    _token: str = Depends(internal_token),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        from src.domain.errors import BadRequestError

        raise BadRequestError("缺少 Idempotency-Key")
    if idempotency_key != body.get("evaluationId"):
        raise IdempotencyKeyMismatchError()

    warning_service.validate_evaluation_request(body)
    response = warning_service.evaluate_and_raise(db, body)

    if response.get("warningId"):
        background.add_task(_dispatch_warning, response["warningId"], body["sample"], x_trace_id)
    return response


def _dispatch_warning(warning_id: str, sample: dict, trace_id: str) -> None:
    import httpx

    from src.infrastructure.db import SessionLocal

    db = SessionLocal()
    try:
        event = warning_service.build_warning_raised_event(db, warning_id, sample, trace_id)
        try:
            warning_client.send_warning_raised(event, trace_id)
            warning_service.mark_warning_sent(db, warning_id)
        except httpx.HTTPError:
            pass
    finally:
        db.close()
