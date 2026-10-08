import httpx
from src.config import settings
from src.domain.errors import UpstreamUnavailableError

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberDClient:
    """D-API-02：Bearer JWT → 操作人权限上下文。

    安全要点（阶段1鉴权闭合，2026-10-06）
    ------------------------------------
    浏览器端点的操作人身份一律来自 D 签发的 Bearer JWT：
    * C 不信任 ``X-User-Id`` 请求头，也不信任报文里的 ``operatorId``；
    * D 不可达时 **fail closed**，不再静默授予"维修主管"全量权限——
      那等于"身份服务一挂，人人都有审批权"。

    失败语义（2026-10-08 修正）
    --------------------------
    * D 返回非 200（令牌无效/过期/用户停用）→ ``None`` → 调用方按 401 处理；
    * D **不可达**（连接失败、超时）→ 抛 ``UpstreamUnavailableError``（503）。
      两者不能混为一谈：把"依赖挂了"报成 401，前端会显示"登录已过期"并
      把用户登出（Windows 上真实踩过，详见 ``src/domain/errors.py`` 注释）。

    ``trust_env=False``：回环调用不读 ``HTTP_PROXY`` / ``ALL_PROXY``。
    Windows 上 Clash/v2rayN 等常全局设代理，httpx 默认会把这类调用也交给
    代理，导致服务间通信失败。
    """

    @staticmethod
    def verify_bearer(token: str, trace_id: str) -> dict | None:
        """经 D-API-02 校验令牌；有效返回权限上下文，无效返回 ``None``。

        :raises UpstreamUnavailableError: D 不可达（503，非凭据问题）。
        """
        try:
            r = httpx.get(
                f"{settings.member_d_base}/api/v1/users/me/access-context",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Trace-Id": trace_id,
                },
                timeout=3.0,
                trust_env=False,
            )
            if r.status_code == 200:
                return r.json()
            return None
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"无法校验访问令牌：身份服务不可达（{settings.member_d_base}）"
            ) from exc


class MemberDNotifier:
    """C-INT-07：提交通知任务"""

    @staticmethod
    def submit_notification(recipients: list[str], template_code: str,
                            variables: dict, trace_id: str) -> bool:
        import uuid
        body = {
            "recipientUserIds": recipients,
            "templateCode": template_code,
            "channel": "IN_APP",
            "variables": variables,
            "businessReference": None,
        }
        try:
            r = httpx.post(
                f"{settings.member_d_base}/api/v1/notifications",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id,
                         "Idempotency-Key": str(uuid.uuid4())},
                json=body, timeout=3.0,
                trust_env=False,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False