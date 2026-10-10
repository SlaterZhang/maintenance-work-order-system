from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from src.application import auth_service, identity_service
from src.domain.errors import BadRequestError
from src.infrastructure.db import get_db
from src.interfaces.http.deps import idempotency_key, internal_token, trace_id

router = APIRouter(prefix="/api/v1", tags=["C-INT-07 通知任务"])


@router.get("/notifications")
def list_notifications(
    recipientUserId: str | None = Query(default=None, max_length=32),
    templateCode: str | None = Query(default=None, max_length=64),
    channel: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """D-API-04：分页查询通知任务（登录身份即可，只读）。

    与 POST 的 ``internalToken`` 口径不同：投递是服务间行为，查询是
    运营人员看板需求，故只要求登录身份，**不暴露也没有必要暴露内部令牌**。
    """
    auth_service.current_user_context(db, authorization)
    return identity_service.list_notifications(
        db,
        recipient_user_id=recipientUserId,
        template_code=templateCode,
        channel=channel,
        page=page,
        page_size=pageSize,
    )


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
