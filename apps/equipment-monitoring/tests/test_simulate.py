"""注入控制台端点：登录身份（Bearer）+ 演示预设 + A→B 评估联动。

阶段1鉴权闭合（2026-10-06）的回归护栏：
* 浏览器不再持 X-Internal-Token 直连内部接口，注入统一走本端点；
* B 评估失败必须如实上抛（不 mock、不静默）——P0-1 的教训。
"""
import uuid

import pytest

from src.interfaces.clients.member_b import MemberBClient
from src.interfaces.clients.member_d import MemberDClient

EQUIPMENT_ID = "EQ-000001"
SIMULATE_URL = f"/api/v1/equipment/{EQUIPMENT_ID}/simulate"


def _auth_headers():
    return {
        "Authorization": "Bearer test-token-USER-A-001",
        "X-Trace-Id": "trace-sim-0001",
        "Idempotency-Key": "key-sim-0001",
    }


@pytest.fixture()
def mock_identity(monkeypatch):
    """打桩 D-API-02：任意 test-token-* 令牌 → 操作员上下文。"""

    def fake_verify_bearer(token, trace_id):
        if not token.startswith("test-token-"):
            return None
        return {
            "userId": token[len("test-token-"):],
            "displayName": "测试操作员",
            "roleCodes": ["EQUIPMENT_OPERATOR"],
            "permissions": ["EQUIPMENT_READ", "TELEMETRY_WRITE"],
            "enabled": True,
        }

    monkeypatch.setattr(
        MemberDClient, "verify_bearer", staticmethod(fake_verify_bearer),
    )


@pytest.fixture()
def mock_evaluation(monkeypatch):
    """打桩 A→B 评估调用，收集请求体。"""
    calls: list[dict] = []

    def fake_evaluate_health(body, trace_id, idem_key):
        calls.append(body)
        return {
            "evaluationId": body["evaluationId"],
            "equipmentId": body["equipmentId"],
            "healthScore": 42.0,
            "riskLevel": "HIGH",
            "modelVersion": "rule-engine-1.0.0",
        }, None

    monkeypatch.setattr(
        MemberBClient, "evaluate_health", staticmethod(fake_evaluate_health),
    )
    return calls


def test_simulate_requires_bearer_token(client):
    """X-Internal-Token / X-User-Id 都不再是浏览器可用的凭据。"""
    r = client.post(
        SIMULATE_URL,
        json={"mode": "ABNORMAL"},
        headers={
            "X-User-Id": "USER-A-001",
            "X-Internal-Token": "dev-internal-token-change-me",
            "Idempotency-Key": "key-noauth-1",
        },
    )
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_simulate_abnormal_ingests_and_evaluates(
        client, mock_identity, mock_evaluation):
    r = client.post(
        SIMULATE_URL, json={"mode": "ABNORMAL"}, headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "ABNORMAL"
    assert body["ingest"]["acceptedCount"] == 1
    assert body["ingest"]["duplicate"] is False
    # 预设值落库（温度 96.7 / 振动 9.8 / 电流 18.3）
    assert body["sample"]["temperatureC"] == pytest.approx(96.7)
    assert body["sample"]["vibrationMmS"] == pytest.approx(9.8)
    assert body["sample"]["currentA"] == pytest.approx(18.3)
    # A→B 评估联动：同一份样本送评，结果原样合入响应
    assert body["evaluation"]["healthScore"] == pytest.approx(42.0)
    assert body["evaluation"]["riskLevel"] == "HIGH"
    assert body["evaluationError"] is None
    assert len(mock_evaluation) == 1
    sent = mock_evaluation[0]
    assert sent["equipmentId"] == EQUIPMENT_ID
    assert sent["sample"] == body["sample"]


def test_simulate_generates_uuid_idem_for_b(client, mock_identity,
                                            mock_evaluation):
    """B 的幂等键要求 UUID：即使客户端键非 UUID，A→B 调用也必须自带。"""
    captured: list[str] = []

    real_evaluate = MemberBClient.evaluate_health

    def spy_evaluate(body, trace_id, idem_key):
        captured.append(idem_key)
        return real_evaluate(body, trace_id, idem_key)

    import src.interfaces.http.simulate as simulate_mod
    simulate_mod.MemberBClient.evaluate_health = staticmethod(spy_evaluate)
    try:
        r = client.post(
            SIMULATE_URL,
            json={"mode": "NORMAL"},
            headers={
                "Authorization": "Bearer test-token-USER-A-001",
                "X-Trace-Id": "trace-sim-uuid",
                "Idempotency-Key": "client-arbitrary-key",   # 非 UUID
            },
        )
        assert r.status_code == 200, r.text
        assert captured, "应产生一次 A→B 评估调用"
        uuid.UUID(captured[0])   # 非法 UUID 会抛 ValueError
    finally:
        simulate_mod.MemberBClient.evaluate_health = staticmethod(real_evaluate)


def test_simulate_normal_preset(client, mock_identity, mock_evaluation):
    r = client.post(
        SIMULATE_URL, json={"mode": "normal"}, headers=_auth_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "NORMAL"
    assert body["sample"]["temperatureC"] == pytest.approx(65.2)
    assert body["sample"]["vibrationMmS"] == pytest.approx(3.4)
    assert body["sample"]["currentA"] == pytest.approx(11.7)


def test_simulate_invalid_mode_400(client, mock_identity):
    r = client.post(
        SIMULATE_URL, json={"mode": "EXPLOSION"}, headers=_auth_headers(),
    )
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


def test_simulate_reports_evaluation_failure(client, mock_identity, monkeypatch):
    """B 评估失败必须如实上抛：evaluation=None + evaluationError 有值。"""

    def broken_evaluate(body, trace_id, idem_key):
        return None, "成员B不可达：ConnectError"

    monkeypatch.setattr(
        MemberBClient, "evaluate_health", staticmethod(broken_evaluate),
    )
    r = client.post(
        SIMULATE_URL, json={"mode": "ABNORMAL"}, headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evaluation"] is None
    assert "成员B不可达" in body["evaluationError"]
    # 遥测本身已落库（A 的职责不受 B 故障影响）
    assert body["ingest"]["acceptedCount"] == 1


def test_simulate_unknown_equipment_404(client, mock_identity):
    r = client.post(
        "/api/v1/equipment/EQ-999999/simulate",
        json={"mode": "ABNORMAL"},
        headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"
