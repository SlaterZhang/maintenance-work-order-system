from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session
import uuid

from src.config import settings
from src.infrastructure.db import get_db
from src.domain.errors import UnauthorizedError, ForbiddenError


def trace_id(x_trace_id: str | None = Header(default=None,
                                              alias="X-Trace-Id")) -> str:
    return x_trace_id or f"trace-{uuid.uuid4().hex[:16]}"


def internal_token(x_internal_token: str | None = Header(
        default=None, alias="X-Internal-Token")):
    if x_internal_token != settings.internal_api_token:
        raise UnauthorizedError("内部令牌无效")
    return x_internal_token


def idempotency_key(idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(400, detail="缺少 Idempotency-Key")
    return idempotency_key


# 简单的用户身份解析（真实环境由成员D校验JWT）
def current_user_id(request: Request) -> str:
    uid = request.headers.get("X-User-Id")
    if not uid:
        raise UnauthorizedError("缺少用户身份")
    return uid


def require_permission(permission: str, user_permissions: list[str]):
    if permission not in user_permissions and "ADMIN_ALL" not in user_permissions:
        raise ForbiddenError(f"缺少权限 {permission}")