"""C-INT-05 维修结论闭环接口测试。

覆盖：``docs/06`` 第 10 节第 5 条的结论映射、eventId 幂等、
迟到结论不覆盖新结论、风险升级、状态审计。
"""

import uuid

import pytest

from src.domain import models
from tests.conftest import (
    ORDER_ID,
    TRACE_ID,
    conclusion_event,
    health_body,
    internal_headers,
    sample_payload,
)

URL = "/api/v1/integration/maintenance-conclusions"
EVAL_URL = "/api/v1/health-evaluations"

HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)


def _create_warning(client) -> str:
    response = client.post(
        EVAL_URL,
        json=health_body(sample=sample_payload(**HIGH_SAMPLE)),
        headers=internal_headers(),
    )
    assert response.status_code == 200, response.text
    return response.json()["warningId"]


def _warning(db, warning_id: str) -> models.Warning:
    db.expire_all()
    return (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )


def _post(client, event, key=None):
    return client.post(URL, json=event, headers=internal_headers(key))


# ---------- 结论映射 ----------
def test_recovered_and_effective_resolves_warning(client, db):
    warning_id = _create_warning(client)
    assert _warning(db, warning_id).status == "LINKED_TO_ORDER"

    response = _post(client, conclusion_event(warning_id))
    assert response.status_code == 202, response.text
    assert response.json() == {
        "accepted": True,
        "duplicate": False,
        "traceId": TRACE_ID,
    }

    warning = _warning(db, warning_id)
    assert warning.status == "RESOLVED"
    assert warning.version == 2  # 建单关联(1) + 闭环(2)


def test_recovered_but_not_effective_marks_false_positive(client, db):
    """结论声称已恢复但标注未生效 -> 标注为误报（模块内判定，见 README）。"""
    warning_id = _create_warning(client)
    _post(
        client,
        conclusion_event(
            warning_id, payload={"result": "RECOVERED", "effective": False}
        ),
    )
    assert _warning(db, warning_id).status == "FALSE_POSITIVE"


def test_partially_recovered_keeps_warning_acknowledged(client, db):
    warning_id = _create_warning(client)
    _post(
        client,
        conclusion_event(
            warning_id, payload={"result": "PARTIALLY_RECOVERED", "effective": True}
        ),
    )
    assert _warning(db, warning_id).status == "ACKNOWLEDGED"


def test_not_recovered_keeps_open_and_escalates_risk(client, db):
    """docs/06 第 10 节第 5 条：保持打开并允许升级风险。"""
    warning_id = _create_warning(client)
    before = _warning(db, warning_id)
    assert before.status == "LINKED_TO_ORDER"
    assert before.risk_level == "HIGH"
    # 必须先取出标量：Session 的身份映射会让 before/after 指向同一个对象
    version_before = before.version

    _post(
        client,
        conclusion_event(
            warning_id, payload={"result": "NOT_RECOVERED", "effective": False}
        ),
    )

    after = _warning(db, warning_id)
    assert after.status == "LINKED_TO_ORDER"   # 状态不变
    assert after.risk_level == "CRITICAL"      # 风险升级一级
    assert after.version == version_before + 1


def test_not_recovered_at_critical_stays_critical(client, db):
    warning_id = _create_warning(client)
    _post(
        client,
        conclusion_event(
            warning_id, payload={"result": "NOT_RECOVERED", "effective": False}
        ),
    )
    _post(
        client,
        conclusion_event(
            warning_id,
            payload={
                "result": "NOT_RECOVERED",
                "effective": False,
                "completedAt": "2026-09-17T12:00:00Z",
            },
        ),
    )
    assert _warning(db, warning_id).risk_level == "CRITICAL"


# ---------- 幂等 ----------
def test_duplicate_event_id_is_ignored(client, db):
    warning_id = _create_warning(client)
    event = conclusion_event(warning_id)

    first = _post(client, event)
    second = _post(client, event)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert db.query(models.MaintenanceConclusion).count() == 1
    assert _warning(db, warning_id).version == 2


def test_same_idempotency_key_returns_cached_result(client, db):
    warning_id = _create_warning(client)
    event = conclusion_event(warning_id)
    key = str(uuid.uuid4())

    first = _post(client, event, key=key)
    second = _post(client, event, key=key)

    assert first.status_code == 202 and second.status_code == 202
    assert first.json() == second.json()
    assert db.query(models.MaintenanceConclusion).count() == 1


def test_same_idempotency_key_different_event_conflicts(client):
    warning_id = _create_warning(client)
    key = str(uuid.uuid4())
    _post(client, conclusion_event(warning_id), key=key)

    other = conclusion_event(warning_id, payload={"result": "NOT_RECOVERED"})
    response = _post(client, other, key=key)

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"


# ---------- 迟到结论 ----------
def test_stale_conclusion_does_not_overwrite_newer_state(client, db):
    """同一 orderId 的最终结论不可被旧版本覆盖（docs/06 第 9 节）。"""
    warning_id = _create_warning(client)

    _post(
        client,
        conclusion_event(
            warning_id,
            payload={"completedAt": "2026-09-17T11:18:00Z"},
        ),
    )
    assert _warning(db, warning_id).status == "RESOLVED"
    version_after_resolve = _warning(db, warning_id).version

    stale = conclusion_event(
        warning_id,
        payload={
            "completedAt": "2026-09-17T09:00:00Z",   # 更早
            "result": "NOT_RECOVERED",
            "effective": False,
        },
    )
    response = _post(client, stale)
    assert response.status_code == 202
    assert response.json()["duplicate"] is False

    warning = _warning(db, warning_id)
    assert warning.status == "RESOLVED"                       # 未被回退
    assert warning.version == version_after_resolve           # 未被改写
    assert db.query(models.MaintenanceConclusion).count() == 2  # 仍然留档


def test_newer_conclusion_is_applied(client, db):
    warning_id = _create_warning(client)
    _post(
        client,
        conclusion_event(
            warning_id, payload={"completedAt": "2026-09-17T11:00:00Z"}
        ),
    )
    _post(
        client,
        conclusion_event(
            warning_id,
            payload={
                "completedAt": "2026-09-17T15:00:00Z",
                "result": "PARTIALLY_RECOVERED",
            },
        ),
    )
    # 第一条已把预警置为 RESOLVED（终态），后续结论只留档
    assert _warning(db, warning_id).status == "RESOLVED"
    assert db.query(models.MaintenanceConclusion).count() == 2


def test_conclusion_on_terminal_warning_is_archived_only(client, db):
    warning_id = _create_warning(client)
    _post(client, conclusion_event(warning_id))
    version = _warning(db, warning_id).version

    _post(
        client,
        conclusion_event(
            warning_id,
            payload={
                "completedAt": "2026-09-18T10:00:00Z",
                "result": "NOT_RECOVERED",
                "effective": False,
            },
        ),
    )
    warning = _warning(db, warning_id)
    assert warning.status == "RESOLVED"
    assert warning.risk_level == "HIGH"      # 终态下不再升级风险
    assert warning.version == version


# ---------- 边界 ----------
def test_conclusion_without_warning_id_is_accepted(client, db):
    """人工报修工单没有预警：接收成功但不改任何预警。"""
    event = conclusion_event(warning_id=None)
    response = _post(client, event)

    assert response.status_code == 202
    assert response.json()["duplicate"] is False
    assert db.query(models.MaintenanceConclusion).count() == 1
    assert db.query(models.Warning).count() == 0


def test_unknown_warning_id_returns_404(client, db):
    response = _post(client, conclusion_event("WARN-20260917-9999"))

    assert response.status_code == 404
    assert response.json()["code"] == "WARNING_NOT_FOUND"
    # 404 时不得留下无法解释的结论记录
    assert db.query(models.MaintenanceConclusion).count() == 0


def test_missing_internal_token_returns_401(client):
    response = client.post(
        URL,
        json=conclusion_event(),
        headers={
            "X-Trace-Id": TRACE_ID,
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_INVALID"


def test_missing_trace_id_returns_400(client):
    response = client.post(
        URL,
        json=conclusion_event(),
        headers={
            "X-Internal-Token": "test-internal-token",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "mutate,field",
    [
        (lambda e: e.__setitem__("eventType", "SomethingElse"), "eventType"),
        (lambda e: e.__setitem__("sourceMember", "MEMBER_A"), "sourceMember"),
        (lambda e: e.__setitem__("schemaVersion", "1.0"), "schemaVersion"),
        (lambda e: e.pop("eventId"), "eventId"),
        (lambda e: e.__setitem__("eventId", "not-a-uuid"), "eventId"),
        (lambda e: e.pop("payload"), "payload"),
        (lambda e: e.__setitem__("extra", 1), "extra"),
        (lambda e: e["payload"].__setitem__("result", "FIXED"), "payload.result"),
        (lambda e: e["payload"].__setitem__("orderId", "WO-1"), "payload.orderId"),
        (lambda e: e["payload"].pop("rootCause"), "payload.rootCause"),
        (lambda e: e["payload"].__setitem__("effective", "yes"), "payload.effective"),
        (lambda e: e["payload"].__setitem__("downtimeMinutes", -1), "payload.downtimeMinutes"),
        (lambda e: e["payload"].__setitem__("submittedBy", "bad"), "payload.submittedBy"),
    ],
)
def test_conclusion_field_validation(client, mutate, field):
    event = conclusion_event()
    mutate(event)

    response = _post(client, event)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert field in {item["field"] for item in body["details"]}


# ---------- 状态审计 ----------
def test_status_history_records_every_change(client, db):
    warning_id = _create_warning(client)
    _post(
        client,
        conclusion_event(
            warning_id, payload={"result": "PARTIALLY_RECOVERED"}
        ),
    )
    _post(
        client,
        conclusion_event(
            warning_id,
            payload={
                "completedAt": "2026-09-17T16:00:00Z",
                "result": "RECOVERED",
                "effective": True,
            },
        ),
    )

    db.expire_all()
    warning = _warning(db, warning_id)
    history = (
        db.query(models.WarningStatusHistory)
        .filter(models.WarningStatusHistory.warning_pk == warning.id)
        .order_by(models.WarningStatusHistory.id)
        .all()
    )
    actions = [(h.action, h.from_status, h.to_status) for h in history]
    assert actions == [
        ("LINK_TO_ORDER", "OPEN", "LINKED_TO_ORDER"),
        ("HOLD_ACKNOWLEDGED", "LINKED_TO_ORDER", "ACKNOWLEDGED"),
        ("RESOLVE", "ACKNOWLEDGED", "RESOLVED"),
    ]
    assert all(h.trace_id == TRACE_ID for h in history)
    assert all(h.operator_id == "USER-C-002" for h in history[1:])


def test_order_id_is_preserved_in_archive(client, db):
    warning_id = _create_warning(client)
    _post(client, conclusion_event(warning_id))

    db.expire_all()
    record = db.query(models.MaintenanceConclusion).one()
    assert record.order_id == ORDER_ID
    assert record.warning_id == warning_id
    assert record.result == "RECOVERED"
    assert record.downtime_minutes == 168
    assert record.submitted_by == "USER-C-002"
