"""停用/启用设备（注入控制台·主数据级下线）——2026-10-07。

验证口径：
* 停用 = ``enabled=false`` + 运行状态联动 STOPPED（停用即停机）+ version+1；
* 停用后遥测注入被拒（409 EQUIPMENT_DISABLED），simulate 与内部
  A-API-05 网关接口共用同一校验——下线设备不得再产生
  “遥测 → 预警 → 工单”链路；
* 启用 = ``enabled=true`` 且运行状态不动；再注入 NORMAL 才恢复 RUNNING
  （与 simulate 的状态复位组合成完整闭环）；
* 参数校验：enabled 非布尔 400、设备不存在 404、无凭据 401。
"""
import uuid

import pytest

from src.interfaces.clients.member_b import MemberBClient
from src.interfaces.clients.member_d import MemberDClient

EQUIPMENT_ID = "EQ-000001"          # 种子：RUNNING
STOPPED_EQUIPMENT_ID = "EQ-000002"  # 种子：STOPPED
TOGGLE_URL = f"/api/v1/equipment/{EQUIPMENT_ID}/enabled"
INTERNAL_TOKEN = "dev-internal-token-change-me"


def _auth_headers():
    return {
        "Authorization": "Bearer test-token-USER-A-001",
        "X-Trace-Id": "trace-enabled-0001",
        "Idempotency-Key": "key-enabled-0001",
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
    """打桩 A→B 评估调用（组合闭环场景用）。"""

    def fake_evaluate_health(body, trace_id, idem_key):
        return {
            "evaluationId": body["evaluationId"],
            "equipmentId": body["equipmentId"],
            "healthScore": 94.7,
            "riskLevel": "LOW",
            "modelVersion": "rule-engine-1.0.0",
        }, None

    monkeypatch.setattr(
        MemberBClient, "evaluate_health", staticmethod(fake_evaluate_health),
    )


def test_disable_equipment_stops_and_marks_disabled(client, mock_identity):
    r = client.post(TOGGLE_URL, json={"enabled": False}, headers=_auth_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is False
    assert body["statusBefore"] == "RUNNING"
    assert body["currentStatus"] == "STOPPED"   # 停用即停机
    assert body["version"] == 1
    eq = client.get(f"/api/v1/equipment/{EQUIPMENT_ID}")
    assert eq.json()["currentStatus"] == "STOPPED"
    assert eq.json()["enabled"] is False


def test_disable_already_stopped_equipment_keeps_version(client, mock_identity):
    """种子即 STOPPED 的设备停用：状态无变化，version 不重复 +1。"""
    url = f"/api/v1/equipment/{STOPPED_EQUIPMENT_ID}/enabled"
    r = client.post(url, json={"enabled": False}, headers=_auth_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is False
    assert body["currentStatus"] == "STOPPED"
    assert body["version"] == 0
    assert client.get(
        f"/api/v1/equipment/{STOPPED_EQUIPMENT_ID}").json()["version"] == 0


def test_disabled_equipment_rejects_simulate(
        client, mock_identity, mock_evaluation):
    """停用后注入控制台拒绝遥测（演示验证点）。"""
    client.post(TOGGLE_URL, json={"enabled": False}, headers=_auth_headers())
    r = client.post(
        f"/api/v1/equipment/{EQUIPMENT_ID}/simulate",
        json={"mode": "ABNORMAL"}, headers=_auth_headers(),
    )
    assert r.status_code == 409
    assert r.json()["code"] == "EQUIPMENT_DISABLED"
    assert EQUIPMENT_ID in r.json()["message"]


def test_disabled_equipment_rejects_internal_telemetry(
        client, mock_identity):
    """内部 A-API-05 网关接口与 simulate 共用停用校验。"""
    client.post(TOGGLE_URL, json={"enabled": False}, headers=_auth_headers())
    sample = {
        "sampleId": str(uuid.uuid4()),
        "measuredAt": "2026-10-07T12:00:00Z",
        "temperatureC": 65.2,
        "vibrationMmS": 3.4,
        "currentA": 11.7,
        "rotationalSpeedRpm": 1450.0,
    }
    r = client.post(
        f"/api/v1/equipment/{EQUIPMENT_ID}/telemetry",
        json={
            "batchId": str(uuid.uuid4()),
            "source": "DEVICE_GATEWAY",
            "samples": [sample],
        },
        headers={
            "X-Internal-Token": INTERNAL_TOKEN,
            "Idempotency-Key": "key-tel-0001",
        },
    )
    assert r.status_code == 409
    assert r.json()["code"] == "EQUIPMENT_DISABLED"


def test_enable_then_normal_restores_running(
        client, mock_identity, mock_evaluation):
    """完整闭环：停用 → 启用（状态不动）→ 注入 NORMAL 恢复运转。"""
    client.post(TOGGLE_URL, json={"enabled": False}, headers=_auth_headers())
    r = client.post(TOGGLE_URL, json={"enabled": True}, headers=_auth_headers())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is True
    assert body["currentStatus"] == "STOPPED"   # 启用不自动恢复运转
    assert body["version"] == 1                 # 状态未变化：不再 +1
    # 注入恢复正常数据 → RUNNING（组合回归 simulate 的状态复位）
    sim = client.post(
        f"/api/v1/equipment/{EQUIPMENT_ID}/simulate",
        json={"mode": "NORMAL"}, headers=_auth_headers(),
    )
    assert sim.status_code == 200, sim.text
    assert sim.json()["equipmentStatusRestored"] is True
    assert sim.json()["equipmentStatusRestoredFrom"] == "STOPPED"
    eq = client.get(f"/api/v1/equipment/{EQUIPMENT_ID}").json()
    assert eq["currentStatus"] == "RUNNING"
    assert eq["enabled"] is True


def test_toggle_rejects_invalid_body(client, mock_identity):
    r = client.post(TOGGLE_URL, json={"enabled": "yes"}, headers=_auth_headers())
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"
    r2 = client.post(TOGGLE_URL, json={}, headers=_auth_headers())
    assert r2.status_code == 400


def test_toggle_unknown_equipment_404(client, mock_identity):
    r = client.post(
        "/api/v1/equipment/EQ-999999/enabled",
        json={"enabled": False}, headers=_auth_headers(),
    )
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"


def test_toggle_requires_bearer_token(client):
    r = client.post(
        TOGGLE_URL,
        json={"enabled": False},
        headers={
            "Authorization": "Basic forged",   # 非有效 Bearer
            "Idempotency-Key": "key-noauth-2",
        },
    )
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"
