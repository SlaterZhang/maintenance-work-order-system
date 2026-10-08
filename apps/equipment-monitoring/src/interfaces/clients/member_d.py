"""调用成员 D 的 D-API-02（身份校验）。

安全要点（阶段1鉴权闭合，2026-10-06）
------------------------------------
浏览器端点的用户身份一律来自 D 签发的 Bearer JWT：
* A 不信任 ``X-User-Id`` 请求头（任何人改一个头就能冒充其他角色）；
* D 不可达时 **fail closed**（拒绝请求），绝不静默放行。

失败语义（2026-10-08 修正）
--------------------------
* D 返回非 200（令牌无效/过期/用户停用）→ ``None`` → 调用方按 401 处理；
* D **不可达**（连接失败、超时）→ 抛 ``UpstreamUnavailableError``（503）。
  两者不能混为一谈：把"依赖挂了"报成 401，前端会显示"登录已过期"并把
  用户登出（Windows 上真实踩过，详见 ``src/domain/errors.py`` 注释）。

``trust_env=False``：不读取 ``HTTP_PROXY`` / ``ALL_PROXY`` 等环境变量。
Windows 上 Clash/v2rayN 等常全局设置代理，而 httpx 默认会把这些**回环调用**
也交给代理，导致服务间通信失败。回环地址不该走代理。
"""

import httpx

from src.config import settings
from src.domain.errors import UpstreamUnavailableError


class MemberDClient:
    """D-API-02：Bearer JWT → 用户权限上下文。"""

    @staticmethod
    def verify_bearer(token: str, trace_id: str) -> dict | None:
        """经 D 校验令牌；有效返回权限上下文，无效返回 ``None``。

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
