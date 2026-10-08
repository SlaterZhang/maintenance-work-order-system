"""D（身份服务）不可达时必须回 503，而不是 401（2026-10-08 Windows 故障回归）。

详见 ``apps/equipment-monitoring/tests/test_upstream_unavailable.py`` 的说明：
Windows 上 ``localhost`` 优先解析 IPv6 ``::1``，而 D 只监听 ``127.0.0.1``，
导致 A/B/C 调 D-API-02 连接失败。若把「连不上」和「令牌无效」都按 401 报，
前端 ``web/js/api.js`` 会误判成登录过期并登出用户。
"""

import inspect

import httpx
import pytest

from src.domain.errors import UpstreamUnavailableError
from src.interfaces.clients import member_d

# conftest 的 autouse ``mock_permissions`` 会把 ``verify_bearer`` 换成假的；
# 本文件验证真实实现，故在 import 时（fixture 生效前）先抓一份原始函数。
_REAL_VERIFY_BEARER = member_d.verify_bearer


@pytest.fixture()
def real_verify(monkeypatch):
    monkeypatch.setattr(member_d, "verify_bearer", _REAL_VERIFY_BEARER)
    return _REAL_VERIFY_BEARER


def _raise_connect_error(*args, **kwargs):
    raise httpx.ConnectError("All connection attempts failed")


def test_unreachable_d_raises_upstream_unavailable(real_verify, monkeypatch):
    monkeypatch.setattr(httpx, "get", _raise_connect_error)
    with pytest.raises(UpstreamUnavailableError) as excinfo:
        real_verify("test-token-USER-B-001", "trace-test-b-0001")
    assert excinfo.value.http_status == 503
    assert excinfo.value.code == "UPSTREAM_UNAVAILABLE"
    assert "身份服务不可达" in excinfo.value.message


def test_timeout_raises_upstream_unavailable(real_verify, monkeypatch):
    def _timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "get", _timeout)
    with pytest.raises(UpstreamUnavailableError):
        real_verify("test-token-USER-B-001", "trace-test-b-0001")


def test_invalid_token_still_returns_none(real_verify, monkeypatch):
    class _Resp:
        status_code = 401

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    assert real_verify("bad-token", "trace-test-b-0001") is None


def test_outbound_calls_do_not_trust_env():
    assert inspect.getsource(member_d).count("trust_env=False") >= 1


def test_api_returns_503_when_identity_service_down(client, monkeypatch):
    """端到端：D 不可达时浏览器端点回 503，前端不会误判"登录过期"。"""
    from tests.conftest import user_headers

    def boom(token, trace_id):
        raise UpstreamUnavailableError("无法校验访问令牌：身份服务不可达（测试桩）")

    monkeypatch.setattr(member_d, "verify_bearer", boom)
    response = client.get("/api/v1/warnings?pageSize=1", headers=user_headers())
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE"
