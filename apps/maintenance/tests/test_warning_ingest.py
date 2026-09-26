"""C-INT-03：预警事件接入（幂等 + 风险门槛 + 自动建单）"""
import pytest

from tests.conftest import (
    INTERNAL_TOKEN, warning_event_payload,
)


HEADERS = {
    "X-Internal-Token": INTERNAL_TOKEN,
    "X-Trace-Id": "trace-test-0001",
    "Idempotency-Key": "11111111-1111-1111-1111-111111111111",
    "Content-Type": "application/json",
}


def _post_warning(client, body, idem=None):
    h = dict(HEADERS)
    if idem:
        h["Idempotency-Key"] = idem
    return client.post("/api/v1/integration/warning-events", json=body, headers=h)


# ---------- 高风险自动建单 ----------
def test_critical_warning_creates_order(client, mock_equipment):
    body = warning_event_payload(risk="CRITICAL")
    r = _post_warning(client, body)
    assert r.status_code == 202
    data = r.json()
    assert data["accepted"] is True
    assert data["duplicate"] is False
    assert data["orderId"].startswith("WO-")
    assert data["traceId"] == "trace-test-0001"


def test_high_warning_creates_order(client, mock_equipment):
    body = warning_event_payload(
        event_id="e2e2e2e2-2222-2222-2222-222222222222",
        warning_id="WARN-20260917-0002",
        risk="HIGH",
    )
    r = _post_warning(client, body)
    assert r.status_code == 202
    assert r.json()["duplicate"] is False


# ---------- 幂等 ----------
def test_same_event_id_returns_same_order(client, mock_equipment):
    body = warning_event_payload()
    r1 = _post_warning(client, body)
    r2 = _post_warning(client, body)
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["orderId"] == r2.json()["orderId"]
    assert r2.json()["duplicate"] is True


def test_same_warning_id_different_event_returns_same_order(
        client, mock_equipment):
    """C-BR-01：WarningId 唯一"""
    body1 = warning_event_payload(
        event_id="aaaaaaaa-0001-0000-0000-000000000000",
        warning_id="WARN-20260917-9999",
    )
    body2 = warning_event_payload(
        event_id="aaaaaaaa-0002-0000-0000-000000000000",
        warning_id="WARN-20260917-9999",  # 同 warningId
    )
    r1 = _post_warning(client, body1)
    r2 = _post_warning(client, body2)
    assert r1.json()["orderId"] == r2.json()["orderId"]
    assert r2.json()["duplicate"] is True


def test_only_one_order_created_for_duplicate(client, db, mock_equipment):
    from src.domain import models
    body = warning_event_payload()
    _post_warning(client, body)
    _post_warning(client, body)
    _post_warning(client, body)
    count = db.query(models.WorkOrder).count()
    assert count == 1


# ---------- 风险门槛 ----------
@pytest.mark.parametrize("risk", ["LOW", "MEDIUM"])
def test_low_medium_rejected(client, mock_equipment, risk):
    body = warning_event_payload(risk=risk)
    r = _post_warning(client, body)
    assert r.status_code == 422
    data = r.json()
    assert data["code"] == "LOW_RISK_NOT_ACCEPTED"


# ---------- 设备不存在 ----------
def test_unknown_equipment_rejected(client, monkeypatch):
    from src.interfaces.clients import member_a

    def fake_none(eq_id, trace_id):
        return None

    monkeypatch.setattr(
        member_a.MemberAClient, "get_equipment",
        staticmethod(fake_none),
    )
    body = warning_event_payload()
    r = _post_warning(client, body)
    assert r.status_code == 404
    assert r.json()["code"] == "EQUIPMENT_NOT_FOUND"


# ---------- 内部令牌 ----------
def test_missing_internal_token_401(client):
    body = warning_event_payload()
    r = client.post("/api/v1/integration/warning-events", json=body, headers={
        "X-Trace-Id": "trace-x",
        "Idempotency-Key": "22222222-2222-2222-2222-222222222222",
    })
    assert r.status_code == 401


# ---------- 建单后字段校验 ----------
def test_order_priority_mapping(client, db, mock_equipment):
    from src.domain import models
    _post_warning(client, warning_event_payload(risk="CRITICAL"))
    _post_warning(client, warning_event_payload(
        event_id="bbbbbbbb-0001-0000-0000-000000000000",
        warning_id="WARN-20260917-0003", risk="HIGH",
    ))
    orders = db.query(models.WorkOrder).all()
    prios = {o.warning_id: o.priority for o in orders}
    assert prios["WARN-20260917-0001"] == "P1"
    assert prios["WARN-20260917-0003"] == "P2"