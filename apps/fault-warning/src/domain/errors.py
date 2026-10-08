"""契约错误类型。

错误码与 HTTP 状态码严格取自 ``docs/06_详细接口约定与联调手册.md`` 第 12 节
的"统一错误码"表，保证 B 的错误响应与项目规范一致。

.. note::
   当前 ``apps/maintenance``（成员 C）使用的是另一套错误码
   （``BAD_REQUEST`` / ``CONFLICT`` / ``IDEMPOTENCY_KEY_CONFLICT`` 等）。
   这属于跨模块不一致，已记录在本模块 README 的"已知不一致"一节，
   需要由 D 组织契约对齐后统一；B 侧先遵循书面规范。
"""

from datetime import datetime, timezone


class ContractError(Exception):
    """契约错误基类：统一落成 ErrorResponse。"""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "内部错误"

    def __init__(
        self,
        message: str | None = None,
        details: list[dict] | None = None,
    ) -> None:
        if message:
            self.message = message
        # details 的元素必须是 FieldViolation：{"field": str, "reason": str}
        self.details: list[dict] = list(details or [])
        super().__init__(self.message)

    def to_response(self, trace_id: str) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "code": self.code,
            "message": self.message,
            "traceId": trace_id,
            "timestamp": timestamp,
            "details": self.details,
        }


# ---------- 400 ----------
class ValidationError(ContractError):
    code = "VALIDATION_ERROR"
    http_status = 400
    message = "请求字段不合法"


# ---------- 401 ----------
class AuthTokenInvalidError(ContractError):
    code = "AUTH_TOKEN_INVALID"
    http_status = 401
    message = "令牌或内部令牌无效"


# ---------- 403 ----------
class PermissionDeniedError(ContractError):
    code = "PERMISSION_DENIED"
    http_status = 403
    message = "当前角色无权执行"


# ---------- 404 ----------
class EquipmentNotFoundError(ContractError):
    code = "EQUIPMENT_NOT_FOUND"
    http_status = 404
    message = "设备不存在"


class WarningNotFoundError(ContractError):
    code = "WARNING_NOT_FOUND"
    http_status = 404
    message = "预警不存在"


# ---------- 409 ----------
class VersionConflictError(ContractError):
    code = "VERSION_CONFLICT"
    http_status = 409
    message = "expectedVersion 已过期"


class IdempotencyConflictError(ContractError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409
    message = "同一 Idempotency-Key 对应了不同请求"


class InvalidStateTransitionError(ContractError):
    code = "INVALID_STATE_TRANSITION"
    http_status = 409
    message = "当前状态不允许该操作"


class WarningAlreadyLinkedError(ContractError):
    code = "WARNING_ALREADY_LINKED"
    http_status = 409
    message = "预警已关联有效工单"


# ---------- 500 ----------
class InternalError(ContractError):
    code = "INTERNAL_ERROR"
    http_status = 500
    message = "内部错误"


# ---------- 503 ----------
class UpstreamUnavailableError(ContractError):
    """依赖服务（D 身份服务等）不可达：503，而不是 401。

    Windows 上曾因 ``.env`` 键名不匹配回落到 ``localhost``（解析为 IPv6
    ``::1``，而服务只监听 ``127.0.0.1``），身份校验连接失败却按
    ``AUTH_TOKEN_INVALID``（401）抛出；前端 ``api.js`` 把"带令牌的 401"
    一律翻译成"登录已过期"并登出，用户被反复踢下线。
    503 与 401 的区别是：这不是"你的令牌无效"，而是"校验方暂时不可用"。
    """

    code = "UPSTREAM_UNAVAILABLE"
    http_status = 503
    message = "依赖服务暂时不可用，请稍后重试"
