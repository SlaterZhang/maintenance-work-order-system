import httpx
from src.config import settings

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberDClient:
    """D-API-02：Bearer JWT → 操作人权限上下文。

    安全要点（阶段1鉴权闭合，2026-10-06）
    ------------------------------------
    浏览器端点的操作人身份一律来自 D 签发的 Bearer JWT：
    * C 不信任 ``X-User-Id`` 请求头，也不信任报文里的 ``operatorId``；
    * D 不可达时 **fail closed**（返回 ``None`` → 401），不再静默授予
      "维修主管"全量权限——那等于"身份服务一挂，人人都有审批权"。
    """

    @staticmethod
    def verify_bearer(token: str, trace_id: str) -> dict | None:
        """经 D-API-02 校验令牌；有效返回权限上下文，否则 ``None``。"""
        try:
            r = httpx.get(
                f"{settings.member_d_base}/api/v1/users/me/access-context",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Trace-Id": trace_id,
                },
                timeout=3.0,
            )
            if r.status_code == 200:
                return r.json()
            return None
        except httpx.HTTPError:
            return None


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
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False