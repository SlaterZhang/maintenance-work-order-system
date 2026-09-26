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