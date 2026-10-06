"""调用成员 D 的 D-API-02（身份校验）。

安全要点（阶段1鉴权闭合，2026-10-06）
------------------------------------
浏览器端点的用户身份一律来自 D 签发的 Bearer JWT：
* A 不信任 ``X-User-Id`` 请求头（任何人改一个头就能冒充其他角色）；
* D 不可达时 **fail closed**（返回 ``None`` → 401），绝不静默放行。
"""

import httpx

from src.config import settings


class MemberDClient:
    """D-API-02：Bearer JWT → 用户权限上下文。"""

    @staticmethod
    def verify_bearer(token: str, trace_id: str) -> dict | None:
        """经 D 校验令牌；有效返回权限上下文，否则 ``None``。"""
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
