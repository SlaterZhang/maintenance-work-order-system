from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from src.application import auth_service, identity_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import internal_token, trace_id

router = APIRouter(prefix="/api/v1/users", tags=["C-INT-06 身份权限上下文"])


@router.get("")
def list_users(
    roleCodes: str | None = Query(
        default=None, max_length=200,
        description="逗号分隔的角色码过滤（如 MAINTENANCE_ENGINEER）"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """D-API-03：分页查询用户摘要（看板派单选人等场景，登录身份即可）"""
    auth_service.current_user_context(db, authorization)
    return identity_service.list_user_summaries(db, roleCodes, page, pageSize)


@router.get("/me/access-context")
def get_current_user_access_context(
    x_trace_id: str = Depends(trace_id),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """D-API-02：当前登录用户的权限上下文（Bearer JWT）"""
    return auth_service.current_user_context(db, authorization)


@router.get("/{user_id}/access-context")
def get_user_access_context(
    user_id: str,
    x_trace_id: str = Depends(trace_id),
    _token: str = Depends(internal_token),
    db: Session = Depends(get_db),
):
    return identity_service.get_access_context(db, user_id)
