class ContractError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "内部错误"

    def __init__(self, message: str | None = None, details: dict | None = None):
        if message:
            self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self, trace_id: str) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "traceId": trace_id,
            "details": self.details,
        }


class BadRequestError(ContractError):
    code = "BAD_REQUEST"
    http_status = 400
    message = "请求字段、枚举或状态不合法"


class UnauthorizedError(ContractError):
    code = "UNAUTHORIZED"
    http_status = 401
    message = "未认证或令牌无效"


class WarningNotFoundError(ContractError):
    code = "WARNING_NOT_FOUND"
    http_status = 404
    message = "预警不存在或已归档"


class IdempotencyKeyMismatchError(ContractError):
    code = "IDEMPOTENCY_KEY_MISMATCH"
    http_status = 400
    message = "Idempotency-Key 必须与事件 eventId 一致"
