import re
import uuid

from fastapi import Header, Request

from src.config import settings
from src.domain.errors import BadRequestError, UnauthorizedError
from src.interfaces.clients.member_d import MemberDClient

USER_ID_PATTERN = r"USER-[A-Z0-9-]{1,27}"


def trace_id(x_trace_id: str | None = Header(default=None, alias="X-Trace-Id")) -> str:
    return x_trace_id or f"trace-{uuid.uuid4().hex[:16]}"


def idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if not idempotency_key:
        raise BadRequestError("缺少 Idempotency-Key 请求头")
    return idempotency_key


def internal_token(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> str:
    if x_internal_token != settings.internal_api_token:
        raise UnauthorizedError("内部令牌无效")
    return x_internal_token


def operator_context(request: Request, trace: str) -> dict:
    """从 ``Authorization: Bearer`` 解析用户身份（经 D-API-02，fail closed）。

    阶段1鉴权闭合（2026-10-06）：A 不再信任 ``X-User-Id`` 请求头。
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
