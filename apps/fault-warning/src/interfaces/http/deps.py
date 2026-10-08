"""FastAPI 依赖：链路追踪、内部令牌、幂等键、身份与权限。

错误类型统一使用 :mod:`src.domain.errors` 中的契约错误，
因此 ``main.py`` 的异常处理器能把它们落成契约 ``ErrorResponse``；
不使用 FastAPI 默认的 ``HTTPException``（其 422/400 响应体不符合契约）。
"""

import re
import uuid

from fastapi import Header, Request

from src.config import settings
from src.domain.errors import (
    AuthTokenInvalidError,
    PermissionDeniedError,
    ValidationError,
)
from src.domain.ids import USER_ID_PATTERN, UUID_PATTERN
from src.interfaces.clients import member_d

TRACE_ID_MIN_LENGTH = 8
TRACE_ID_MAX_LENGTH = 64
IDEMPOTENCY_KEY_MAX_LENGTH = 64


def trace_id(
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> str:
    """可选链路标识（``TraceIdHeader``）：缺失时本地生成。"""
    return x_trace_id or f"trace-{uuid.uuid4().hex[:16]}"


def required_trace_id(
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> str:
    """服务间接口要求调用方必须携带 ``X-Trace-Id``（``RequiredTraceIdHeader``）。"""
    if not x_trace_id or not (
        TRACE_ID_MIN_LENGTH <= len(x_trace_id) <= TRACE_ID_MAX_LENGTH
    ):
        raise ValidationError(
            "缺少或非法的 X-Trace-Id",
            details=[
                {
                    "field": "X-Trace-Id",
                    "reason": (
                        f"必填且长度必须在 {TRACE_ID_MIN_LENGTH}.."
                        f"{TRACE_ID_MAX_LENGTH} 之间"
                    ),
                }
            ],
        )
    return x_trace_id


def internal_token(
    x_internal_token: str | None = Header(
        default=None, alias="X-Internal-Token"
    ),
) -> str:
    """服务间鉴权（``internalToken``）。"""
    if x_internal_token != settings.internal_api_token:
        raise AuthTokenInvalidError("内部令牌无效")
    return x_internal_token


def idempotency_key(
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key"
    ),
) -> str:
    """写操作幂等键：必填且必须为 UUID（契约 ``IdempotencyKeyHeader``）。"""
    if not idempotency_key:
        raise ValidationError(
            "缺少 Idempotency-Key",
            details=[
                {"field": "Idempotency-Key", "reason": "写操作必须携带，且值为 UUID"}
            ],
        )
    if len(idempotency_key) > IDEMPOTENCY_KEY_MAX_LENGTH or not re.fullmatch(
        UUID_PATTERN, idempotency_key
    ):
        raise ValidationError(
            "Idempotency-Key 不是合法 UUID",
            details=[
                {
                    "field": "Idempotency-Key",
                    "reason": "必须为 UUID，例如 6cb7fef3-bcae-42de-8b57-ef54d3431003",
                }
            ],
        )
    return idempotency_key


def current_user_context(request: Request, trace: str) -> dict:
    """从 ``Authorization: Bearer`` 解析登录用户（经 D-API-02 校验）。

    阶段1鉴权闭合（2026-10-06）：浏览器端点不再信任直发的 ``X-User-Id``
    头——任何人改一个请求头就能冒充其他角色。身份唯一来源是 D 签发并
    验签的 JWT；权限上下文由 D-API-02 一并返回，无需二次查询。
    ``X-User-Id`` 仅保留在服务间内部调用通道（配合内部令牌）。
    """
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthTokenInvalidError("缺少 Bearer 访问令牌")
    token = authorization[len("Bearer "):].strip()
    context = member_d.verify_bearer(token, trace)
    if context is None:
        raise AuthTokenInvalidError("访问令牌无效或已过期")
    user_id = context.get("userId") or ""
    if not re.fullmatch(USER_ID_PATTERN, user_id):
        raise AuthTokenInvalidError("访问令牌返回的用户标识格式非法")
    if context.get("enabled") is False:
        raise AuthTokenInvalidError(f"用户 {user_id} 已停用")
    return context


def require_permission(context: dict, permission: str) -> None:
    """校验登录用户是否具备指定权限码；上下文来自 D-API-02。

    ``docs/06`` 第 13 节明确：按**权限码**校验，不按中文角色名判断。
    """
    permissions = list(context.get("permissions") or [])
    if permission not in permissions and "ADMIN_ALL" not in permissions:
        raise PermissionDeniedError(f"缺少权限 {permission}")
