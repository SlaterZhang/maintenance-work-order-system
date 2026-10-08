import uuid

from fastapi import Header

from src.config import settings
from src.domain.errors import BadRequestError, UnauthorizedError


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
