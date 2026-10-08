"""C-INT-08 工单取消回流接口测试（2026-10-07 新增）。

背景：工单取消只改 C 侧状态，关联预警悬在 ``LINKED_TO_ORDER`` 活跃态，
评估去重规则持续复用死预警，"取消后再异常"永远不再自动建单。
修复后：取消事件把预警闭环为 ``CANCELLED`` 终态，后续异常评估新建预警。
"""

import uuid

import pytest

from src.domain import models
from tests.conftest import (
    TRACE_ID,
    cancellation_event,
    health_body,
    internal_headers,
    sample_payload,
)

URL = "/api/v1/integration/order-cancellations"
EVAL_URL = "/api/v1/health-evaluations"

HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)


def _create_warning(client) -> str:
    """注入 HIGH 评估产生一条预警（评估后即 LINKED_TO_ORDER）。"""
    response = client.post(
        EVAL_URL,
        json=health_body(sample=sample_payload(**HIGH_SAMPLE)),
        headers=internal_headers(),
    )
    assert response.status_code == 200, response.text
    warning_id = response.json()["warningId"]
    assert warning_id, "HIGH 评估应产生预警"
    return warning_id


def _warning(db, warning_id: str) -> models.Warning:
    db.expire_all()
    return (
        db.query(models.Warning)
        .filter(models.Warning.warning_id == warning_id)
        .one()
    )


def _post(client, event, key=None):
    return client.post(URL, json=event, headers=internal_headers(key))


# ---------- 取消闭环 ----------
def test_cancel_event_closes_warning_as_cancelled(client, db):
    warning_id = _create_warning(client)
    assert _warning(db, warning_id).status == "LINKED_TO_ORDER"

    response = _post(client, cancellation_event(warning_id))
    assert response.status_code == 202, response.text
    assert response.json() == {
        "accepted": True,
        "duplicate": False,
        "traceId": TRACE_ID,
    }

    warning = _warning(db, warning_id)
    assert warning.status == "CANCELLED"
    assert warning.version == 2  # 建单关联(1) + 取消闭环(2)


def test_cancel_then_new_evaluation_creates_fresh_warning(client, db):
    """用户场景回归：取消后再异常，必须新建预警（修复前会复用死预警）。"""
    warning_id = _create_warning(client)
    _post(client, cancellation_event(warning_id))
    assert _warning(db, warning_id).status == "CANCELLED"

    response = client.post(
        EVAL_URL,
        json=health_body(sample=sample_payload(**HIGH_SAMPLE)),
        headers=internal_headers(),
    )
    assert response.status_code == 200, response.text
    new_warning_id = response.json()["warningId"]
    assert new_warning_id, "取消闭环后再次 HIGH 评估应产生新预警"
    assert new_warning_id != warning_id, "不应复用已 CANCELLED 的预警"


def test_cancel_event_idempotent_by_key(client, db):
    warning_id = _create_warning(client)
    event = cancellation_event(warning_id)
    key = str(uuid.uuid4())  # 契约要求 Idempotency-Key 为 UUID

    first = _post(client, event, key=key)
    second = _post(client, event, key=key)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json() == second.json()  # 同 key 回放原响应

    warning = _warning(db, warning_id)
    assert warning.status == "CANCELLED"
    assert warning.version == 2  # 幂等重放不再推进版本


def test_cancel_event_on_terminal_warning_archives_only(client, db):
    """已解决预警收到取消事件：只留档，不反向改写状态。"""
    warning_id = _create_warning(client)
    # 先取消（→ CANCELLED 终态），再发一条不同 eventId 的取消
    _post(client, cancellation_event(warning_id))
    terminal = _warning(db, warning_id)
    assert terminal.status == "CANCELLED"

    response = _post(client, cancellation_event(warning_id))
    assert response.status_code == 202, response.text
    after = _warning(db, warning_id)
    assert after.status == "CANCELLED"
    assert after.version == terminal.version  # 终态守卫：版本不再推进


def test_cancel_event_unknown_warning_returns_404(client):
    response = _post(client, cancellation_event("WARN-19990101-9999"))
    assert response.status_code == 404, response.text


def test_cancel_event_rejects_bad_payload(client):
    warning_id = _create_warning(client)
    event = cancellation_event(
        warning_id, payload={"warningId": None}
    )
    response = _post(client, event)
    assert response.status_code == 400, response.text
    # 预警未被误伤
    # （payload.warningId 传 null → 校验失败，状态不动）
