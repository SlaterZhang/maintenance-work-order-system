from datetime import datetime, timezone


class ContractError(Exception):
    """契约错误基类，落成 ErrorResponse"""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "内部错误"

    def __init__(self, message: str | None = None,
                 details: list[dict] | None = None):
        if message:
            self.message = message
        self.details = details or []
        super().__init__(self.message)

    def to_response(self, trace_id: str) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "traceId": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": self.details,
        }


class BadRequestError(ContractError):
    code = "BAD_REQUEST"
    http_status = 400
    message = "请求字段不合法"


class UnauthorizedError(ContractError):
    code = "UNAUTHORIZED"
    http_status = 401
    message = "未认证或令牌无效"


class ForbiddenError(ContractError):
    code = "FORBIDDEN"
    http_status = 403
    message = "缺少该操作所需权限"


class NotFoundError(ContractError):
    code = "NOT_FOUND"
    http_status = 404
    message = "对象不存在"


class ConflictError(ContractError):
    code = "CONFLICT"
    http_status = 409
    message = "状态冲突或版本不一致"


class IdempotencyConflictError(ContractError):
    code = "IDEMPOTENCY_KEY_CONFLICT"
    http_status = 409
    message = "同一 Idempotency-Key 对应了不同请求"


class LowRiskNotAcceptedError(ContractError):
    code = "LOW_RISK_NOT_ACCEPTED"
    http_status = 422
    message = "LOW 或 MEDIUM 预警不满足自动建单条件"


class WorkOrderNotFoundError(NotFoundError):
    code = "WORK_ORDER_NOT_FOUND"
    message = "工单不存在"


class SparePartNotFoundError(NotFoundError):
    code = "SPARE_PART_NOT_FOUND"
    message = "备件不存在"


class SpareRequestNotFoundError(NotFoundError):
    code = "SPARE_REQUEST_NOT_FOUND"
    message = "备件申请不存在"


class InsufficientStockError(ConflictError):
    code = "INSUFFICIENT_STOCK"
    message = "可用库存不足"


class InvalidTransitionError(ConflictError):
    code = "INVALID_STATE_TRANSITION"
    message = "当前状态不允许该操作"


class EquipmentNotFoundError(ContractError):
    code = "EQUIPMENT_NOT_FOUND"
    http_status = 404
    message = "设备不存在"


class UpstreamUnavailableError(ContractError):
    """依赖服务（D 身份服务等）不可达：503，而不是 401。

    Windows 上曾因 B 服务的 ``.env`` 键名不匹配回落到 ``localhost``（解析为
    IPv6 ``::1``，而服务只监听 ``127.0.0.1``），身份校验连接失败却按 401 抛出；
    前端 ``api.js`` 把"带令牌的 401"一律翻译成"登录已过期"并登出。
    503 用来区分"校验方暂时不可用"与"你的令牌无效"。
    """

    code = "UPSTREAM_UNAVAILABLE"
    http_status = 503
    message = "依赖服务暂时不可用，请稍后重试"
