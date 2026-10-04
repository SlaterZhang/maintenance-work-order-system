"""调用成员 C 的 C-INT-03：发送 ``WarningRaised``。

契约要点（``docs/06`` 第 9 节）
------------------------------
* 事件重试时 URL、``eventId``、``Idempotency-Key`` 和请求体必须**完全相同**，
  因此这里的 ``Idempotency-Key`` 固定使用 ``eventId``，
  而不是每次调用新生成一个 UUID（那会让接收端的幂等完全失效）。
* 事件包络的 ``eventId`` 由 outbox 行持有，重试沿用同一个值。
"""

import httpx

from src.config import settings

WARNING_EVENTS_PATH = "/api/v1/integration/warning-events"


def warning_events_url() -> str:
    return f"{settings.maintenance_service_url}{WARNING_EVENTS_PATH}"


def send_warning_raised(
    event: dict, trace_id: str, event_id: str
) -> tuple[bool, dict | None, str | None]:
    """把 ``WarningRaised`` 事件投递给 C。

    :returns: ``(是否成功, 响应体或 None, 失败原因或 None)``
        成功包含 HTTP 200/202；C 返回的 ``orderId`` 会用于回填 ``linkedOrderId``。
    """
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Trace-Id": trace_id,
        "Idempotency-Key": event_id,  # 重试保持不变
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            warning_events_url(),
            headers=headers,
            json=event,
            timeout=settings.client_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        return False, None, f"{type(exc).__name__}: {exc}"

    if response.status_code in (200, 202):
        try:
            return True, response.json(), None
        except ValueError:
            return True, None, None

    return False, None, f"HTTP {response.status_code}: {response.text[:200]}"
