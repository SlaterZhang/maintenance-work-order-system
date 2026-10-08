"""D（身份服务）不可达时必须回 503，而不是 401（2026-10-08 Windows 故障回归）。

背景
----
Windows 上 B 服务的 ``.env`` 键名被启动脚本写错，回连地址落回 ``localhost``；
Windows 把 ``localhost`` 优先解析成 IPv6 ``::1``，而 D 只监听 ``127.0.0.1``，
于是 A/B/C 调 D-API-02 全部连接失败。旧实现把「连接失败」与「令牌无效」
都按 401 抛出，前端 ``web/js/api.js`` 见 401 就 ``handleSessionExpired()``，
用户被反复登出、怎么都登不进去。

修好后语义必须分开：
* D 返回非 200（令牌无效/过期/停用）→ ``None`` → 调用方 401；
* D **不可达**（ConnectError/Timeout）→ ``UpstreamUnavailableError`` → 503。
"""

import inspect

import httpx
import pytest

from src.domain.errors import UpstreamUnavailableError
from src.interfaces.clients.member_d import MemberDClient

# conftest 的 autouse ``mock_identity`` 会把 ``verify_bearer`` 换成假的；
# 本文件要验证真实实现，故在 import 时（fixture 生效前）先抓一份原始函数。
_REAL_VERIFY_BEARER = MemberDClient.verify_bearer


@pytest.fixture()
def real_client(monkeypatch):
    """把 A 的 D 客户端还原成真实实现（覆盖 conftest 的桩）。"""
    monkeypatch.setattr(
        MemberDClient, "verify_bearer", staticmethod(_REAL_VERIFY_BEARER)
    )
    return MemberDClient


def _raise_connect_error(*args, **kwargs):
    raise httpx.ConnectError("All connection attempts failed")


def _raise_timeout(*args, **kwargs):
    raise httpx.ReadTimeout("timed out")


def test_unreachable_d_raises_upstream_unavailable(real_client, monkeypatch):
    """连接失败 → 503 UPSTREAM_UNAVAILABLE，而不是 None(→401)。"""
    monkeypatch.setattr(httpx, "get", _raise_connect_error)
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        real_client.verify_bearer("test-token-USER-A-001", "trace-test-0001")
    assert excinfo.value.http_status == 503
    assert excinfo.value.code == "UPSTREAM_UNAVAILABLE"
    assert "身份服务不可达" in excinfo.value.message


def test_timeout_raises_upstream_unavailable(real_client, monkeypatch):
    monkeypatch.setattr(httpx, "get", _raise_timeout)
    with pytest.raises(UpstreamUnavailableError):
        real_client.verify_bearer("test-token-USER-A-001", "trace-test-0001")


def test_invalid_token_still_returns_none(real_client, monkeypatch):
    """D 明确回 401/403（凭据问题）→ 仍返回 None，由调用方给 401。"""
    class _Resp:
        status_code = 401

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    assert real_client.verify_bearer("bad-token", "trace-test-0001") is None


def test_outbound_calls_do_not_trust_env():
    """回环调用不得读取 HTTP_PROXY（Windows 全局代理会劫持服务间通信）。"""
    assert inspect.getsource(MemberDClient).count("trust_env=False") >= 1


def test_api_returns_503_when_identity_service_down(client, monkeypatch):
    """端到端：D 不可达时浏览器端点回 503，前端就不会误判"登录过期"。"""
    def boom(token, trace_id):
        raise UpstreamUnavailableError("无法校验访问令牌：身份服务不可达（测试桩）")

    monkeypatch.setattr(MemberDClient, "verify_bearer", staticmethod(boom))
    response = client.get("/api/v1/equipment?pageSize=1")
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "UPSTREAM_UNAVAILABLE"
