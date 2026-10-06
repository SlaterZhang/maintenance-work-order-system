import re

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session
import uuid

from src.config import settings
from src.infrastructure.db import get_db
from src.domain.errors import UnauthorizedError, ForbiddenError
from src.interfaces.clients.member_d import MemberDClient

USER_ID_PATTERN = r"USER-[A-Z0-9-]{1,27}"


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


def operator_context(request: Request, trace: str) -> dict:
    """从 ``Authorization: Bearer`` 解析操作人身份与权限（经 D-API-02）。

    阶段1鉴权闭合（2026-10-06）：命令操作人不再取自报文或 ``X-User-Id``
    请求头——任何人改一个头就能冒充其他角色。服务端以 D 验签后的
    JWT 身份为准，报文中的 ``operatorId`` 仅作展示兼容。
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("缺少 Bearer 访问令牌")
    token = authorization[len("Bearer "):].strip()
    context = MemberDClient.verify_bearer(token, trace)
    if not context:
        raise UnauthorizedError("访问令牌无效或已过期")
    user_id = context.get("userId") or ""
    if not re.fullmatch(USER_ID_PATTERN, user_id):
        raise UnauthorizedError("访问令牌返回的用户标识格式非法")
    if context.get("enabled") is False:
        raise UnauthorizedError(f"用户 {user_id} 已停用")
    return context


def require_permission(permission: str, user_permissions: list[str]):
    if permission not in user_permissions and "ADMIN_ALL" not in user_permissions:
        raise ForbiddenError(f"缺少权限 {permission}")