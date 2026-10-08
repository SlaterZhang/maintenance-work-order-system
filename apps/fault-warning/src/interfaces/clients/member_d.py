"""调用成员 D 的 C-INT-08（权限上下文）与 C-INT-07（通知）。

安全要点
--------
成员 C 的实现会在 D 不可达时**静默返回"维修主管"权限**，
这等于"身份服务一挂，所有人自动获得审批权"。B 侧不复制这个行为：

* mock 降级必须由 ``ALLOW_CLIENT_MOCK`` 显式打开；
* 降级返回的是 B 接口所需的**最小权限集**（预警分析员），
  不包含任何审批、发料、工单类权限；
* 关闭 mock 时 D 不可达 -> 503 ``UPSTREAM_UNAVAILABLE``（fail closed）。

失败语义（2026-10-08 修正）
--------------------------
D 返回非 200（令牌无效/过期/用户停用）才是 401 ``AUTH_TOKEN_INVALID``；
D **不可达**（连接失败、超时）是 503 ``UPSTREAM_UNAVAILABLE``。早期把两者
都按 401 抛出，前端 ``api.js`` 会把"依赖服务挂了"显示成"登录已过期"并登出，
Windows 上真实踩过（详见 ``src/domain/errors.py`` 注释）。

``trust_env=False``：不读取 ``HTTP_PROXY`` / ``ALL_PROXY`` 等环境变量。
Windows 上 Clash/v2rayN 等常全局设代理，httpx 默认会把**回环调用**也交给
代理，导致服务间通信失败；回环地址不该走代理。
"""

import uuid

import httpx

from src.config import settings
from src.domain.errors import AuthTokenInvalidError, UpstreamUnavailableError

ACCESS_CONTEXT_PATH = "/api/v1/users/{user_id}/access-context"
ME_ACCESS_CONTEXT_PATH = "/api/v1/users/me/access-context"
NOTIFICATIONS_PATH = "/api/v1/notifications"

# 契约 docs/06 第 13 节：WARNING_ANALYST 的固定权限集
WARNING_ANALYST_PERMISSIONS: list[str] = [
    "EQUIPMENT_READ",
    "WARNING_READ",
    "WARNING_ACKNOWLEDGE",
]


def access_context_url(user_id: str) -> str:
    return f"{settings.integration_service_url}{ACCESS_CONTEXT_PATH.format(user_id=user_id)}"


def me_access_context_url() -> str:
    return f"{settings.integration_service_url}{ME_ACCESS_CONTEXT_PATH}"


def notifications_url() -> str:
    return f"{settings.integration_service_url}{NOTIFICATIONS_PATH}"


def verify_bearer(token: str, trace_id: str) -> dict | None:
    """经 D-API-02 校验 Bearer JWT，返回该用户的权限上下文。

    D 是唯一的身份权威：B 不自行解析 JWT，而是携带令牌调用 D-API-02，
    由 D 验签后返回 userId / roleCodes / permissions / enabled，
    身份与权限一次取得，无需二次查询。

    :returns: 权限上下文；令牌无效、过期或用户停用时 D 返回 401 → ``None``。
    :raises UpstreamUnavailableError: D 不可达且未开启 mock 降级（fail closed）。
    """
    try:
        response = httpx.get(
            me_access_context_url(),
            headers={
                "Authorization": f"Bearer {token}",
                "X-Trace-Id": trace_id,
            },
            timeout=settings.client_timeout_seconds,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        if settings.allow_client_mock:
            return _mock_access_context("USER-B-001")
        raise UpstreamUnavailableError(
            f"无法校验访问令牌：身份服务不可达（{settings.integration_service_url}）"
        ) from exc
    if response.status_code == 200:
        return response.json()
    return None


def get_access_context(user_id: str, trace_id: str) -> dict | None:
    """查询用户权限上下文。

    :returns: 权限上下文字典；用户在 D 中不存在时返回 ``None``。
    :raises UpstreamUnavailableError: D 不可达且未开启 mock 降级。
    """
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Trace-Id": trace_id,
    }
    try:
        response = httpx.get(
            access_context_url(user_id),
            headers=headers,
            timeout=settings.client_timeout_seconds,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        if settings.allow_client_mock:
            return _mock_access_context(user_id)
        raise UpstreamUnavailableError(
            f"无法校验用户身份：身份服务不可达（{settings.integration_service_url}）"
        ) from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        if settings.allow_client_mock:
            return _mock_access_context(user_id)
        raise AuthTokenInvalidError(
            f"身份服务返回 HTTP {response.status_code}，无法校验用户"
        )
    return response.json()


def submit_notification(
    recipients: list[str],
    template_code: str,
    variables: dict,
    trace_id: str,
    idempotency_key: str,
) -> tuple[bool, str | None]:
    """提交通知任务（C-INT-07）。

    失败**不阻塞**主业务：调用方把结果记入 outbox，稍后重试
    （``docs/06`` 第 10 节第 7 条）。

    :returns: ``(是否成功, 失败原因)``
    """
    body = {
        "recipientUserIds": recipients,
        "templateCode": template_code,
        "channel": "IN_APP",
        "variables": variables,
        "businessReference": variables.get("warningId"),
    }
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Trace-Id": trace_id,
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }
    try:
        response = httpx.post(
            notifications_url(),
            headers=headers,
            json=body,
            timeout=settings.client_timeout_seconds,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if response.status_code in (200, 202):
        return True, None
    return False, f"HTTP {response.status_code}: {response.text[:200]}"


def _mock_access_context(user_id: str) -> dict:
    """本地开发用的最小权限上下文（预警分析员），不含任何审批类权限。"""
    return {
        "userId": user_id,
        "displayName": f"本地开发用户-{user_id}",
        "roleCodes": ["WARNING_ANALYST"],
        "permissions": list(WARNING_ANALYST_PERMISSIONS),
        "organization": "质量管理部",
        "enabled": True,
        "source": "LOCAL_MOCK",
    }


def new_notification_idempotency_key() -> str:
    """通知任务的幂等键；由调用方在登记 outbox 时固定一次并复用。"""
    return str(uuid.uuid4())
