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


class EquipmentNotFoundError(ContractError):
    code = "EQUIPMENT_NOT_FOUND"
    http_status = 404
    message = "设备不存在"


class EquipmentDisabledError(ContractError):
    code = "EQUIPMENT_DISABLED"
    http_status = 409
    message = "设备已停用"


class IdempotencyKeyMismatchError(ContractError):
    code = "IDEMPOTENCY_KEY_MISMATCH"
    http_status = 400
    message = "Idempotency-Key 必须与事件 eventId 一致"


class UpstreamUnavailableError(ContractError):
    """依赖服务（如 D 身份服务）不可达：503，而不是 401。

    Windows 上 B 曾因 ``.env`` 键名不匹配回落到 ``localhost``（解析为 IPv6
    ``::1``，而服务只监听 ``127.0.0.1``），身份校验连接失败却抛 401；前端
    ``api.js`` 把"带令牌的 401"一律翻译成"登录已过期"，用户被反复踢下线。
    用 503 明确区分"校验方不可用"与"你的令牌无效"，避免同类误报。
    """

    code = "UPSTREAM_UNAVAILABLE"
    http_status = 503
    message = "依赖服务暂时不可用，请稍后重试"
