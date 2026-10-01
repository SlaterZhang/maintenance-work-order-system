"""B-API-01 ~ B-API-03 预警查询与确认接口测试。

覆盖：权限校验、过滤与分页、契约字段完整性、乐观锁、状态迁移冲突、幂等。
"""

import uuid

import pytest

from src.interfaces.clients import member_c, member_d
from tests.conftest import (
    EQUIPMENT_ID,
    USER_ID,
    health_body,
    internal_headers,
    sample_payload,
    user_headers,
)

LIST_URL = "/api/v1/warnings"
EVAL_URL = "/api/v1/health-evaluations"

HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)
OVERHEAT_SAMPLE = dict(
    temperatureC=95.0, vibrationMmS=1.0, currentA=1.0, rotationalSpeedRpm=1500.0
)


def _create_warning(client, sample=None, equipment_id=EQUIPMENT_ID) -> str:
    body = health_body(
        equipmentId=equipment_id, sample=sample_payload(**(sample or HIGH_SAMPLE))
    )
    response = client.post(EVAL_URL, json=body, headers=internal_headers())
    assert response.status_code == 200, response.text
    warning_id = response.json()["warningId"]
    assert warning_id
    return warning_id


def _create_open_warning(client, monkeypatch) -> str:
    """构造一条仍处于 OPEN 的预警。

    让 C 在本次评估时不可达，事件留在 outbox，预警不会被推进到
    ``LINKED_TO_ORDER``，从而可以测试"从 OPEN 确认"的路径。
    """
    monkeypatch.setattr(
        member_c,
        "send_warning_raised",
        lambda event, trace_id, event_id: (False, None, "C 暂时不可达"),
    )
    return _create_warning(client)


def _ack(client, warning_id, expected_version=0, key=None, **extra):
    body = {
        "operatorId": USER_ID,
        "expectedVersion": expected_version,
        "comment": None,
    }
    body.update(extra)
    return client.post(
        f"{LIST_URL}/{warning_id}/acknowledgements",
        json=body,
        headers=user_headers(idempotency_key=key or str(uuid.uuid4())),
    )


# ---------- B-API-01 列表 ----------
def test_list_returns_contract_warning_shape(client):
    warning_id = _create_warning(client)

    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 200, response.text
    data = response.json()

    assert set(data) == {"items", "page", "pageSize", "total", "totalPages"}
    assert data["total"] == 1
    assert data["page"] == 1 and data["pageSize"] == 20 and data["totalPages"] == 1

    item = data["items"][0]
    assert set(item) == {
        "warningId",
        "equipmentId",
        "riskLevel",
        "healthScore",
        "suspectedFault",
        "recommendedAction",
        "status",
        "warningAt",
        "modelVersion",
        "linkedOrderId",
        "acknowledgedBy",
        "acknowledgedAt",
        "version",
    }
    assert item["warningId"] == warning_id
    # 可为空字段必须显式返回 null，不得省略
    assert item["acknowledgedBy"] is None
    assert item["acknowledgedAt"] is None
    assert item["warningAt"].endswith("Z")


def test_list_requires_user_identity(client):
    response = client.get(LIST_URL, headers={"X-Trace-Id": "trace-x"})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_TOKEN_INVALID"


def test_list_requires_warning_read_permission(client, monkeypatch):
    monkeypatch.setattr(
        member_d,
        "get_access_context",
        lambda user_id, trace_id: {
            "userId": user_id,
            "roleCodes": ["EQUIPMENT_OPERATOR"],
            "permissions": ["EQUIPMENT_READ"],
            "enabled": True,
        },
    )
    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_list_rejects_malformed_user_id(client):
    response = client.get(LIST_URL, headers=user_headers(user_id="bad-user"))
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_admin_all_bypasses_permission(client, monkeypatch):
    monkeypatch.setattr(
        member_d,
        "get_access_context",
        lambda user_id, trace_id: {
            "userId": user_id,
            "permissions": ["ADMIN_ALL"],
            "enabled": True,
        },
    )
    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 200


def test_list_disabled_user_is_rejected(client, monkeypatch):
    monkeypatch.setattr(
        member_d,
        "get_access_context",
        lambda user_id, trace_id: {"userId": user_id, "enabled": False},
    )
    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 401


def test_unknown_user_is_rejected(client, monkeypatch):
    monkeypatch.setattr(
        member_d, "get_access_context", lambda user_id, trace_id: None
    )
    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 401


def test_list_filters(client):
    _create_warning(client, equipment_id="EQ-000001")
    _create_warning(
        client, sample=OVERHEAT_SAMPLE, equipment_id="EQ-000002"
    )

    by_equipment = client.get(
        f"{LIST_URL}?equipmentId=EQ-000002", headers=user_headers()
    ).json()
    assert by_equipment["total"] == 1
    assert by_equipment["items"][0]["equipmentId"] == "EQ-000002"

    by_risk = client.get(f"{LIST_URL}?riskLevel=HIGH", headers=user_headers()).json()
    assert by_risk["total"] == 2

    by_status = client.get(
        f"{LIST_URL}?status=RESOLVED", headers=user_headers()
    ).json()
    assert by_status["total"] == 0
    assert by_status["items"] == []
    assert by_status["totalPages"] == 0


@pytest.mark.parametrize(
    "query,field",
    [
        ("equipmentId=EQ-1", "equipmentId"),
        ("riskLevel=URGENT", "riskLevel"),
        ("status=UNKNOWN", "status"),
    ],
)
def test_list_invalid_filter_returns_400(client, query, field):
    response = client.get(f"{LIST_URL}?{query}", headers=user_headers())
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert field in {item["field"] for item in body["details"]}


def test_list_pagination(client):
    for equipment in ("EQ-000001", "EQ-000002", "EQ-000003"):
        _create_warning(client, equipment_id=equipment)

    first = client.get(f"{LIST_URL}?page=1&pageSize=2", headers=user_headers()).json()
    assert first["total"] == 3
    assert first["totalPages"] == 2
    assert len(first["items"]) == 2

    second = client.get(f"{LIST_URL}?page=2&pageSize=2", headers=user_headers()).json()
    assert len(second["items"]) == 1


def test_list_orders_by_warning_at_desc(client):
    older = _create_warning(client, equipment_id="EQ-000010")
    newer = _create_warning(client, equipment_id="EQ-000011")

    ids = [
        item["warningId"]
        for item in client.get(LIST_URL, headers=user_headers()).json()["items"]
    ]
    # 两次评估的 warningAt 相同（同一请求时间戳来源），次要排序键为 id 倒序
    assert set(ids) == {older, newer}
    assert ids[0] == newer


def test_list_page_size_out_of_range_is_400(client):
    response = client.get(f"{LIST_URL}?pageSize=999", headers=user_headers())
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_page_zero_is_400(client):
    response = client.get(f"{LIST_URL}?page=0", headers=user_headers())
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------- B-API-02 详情 ----------
def test_get_warning_detail(client):
    warning_id = _create_warning(client)
    response = client.get(f"{LIST_URL}/{warning_id}", headers=user_headers())
    assert response.status_code == 200
    assert response.json()["warningId"] == warning_id


def test_get_unknown_warning_404(client):
    response = client.get(
        f"{LIST_URL}/WARN-20260917-9999", headers=user_headers()
    )
    assert response.status_code == 404
    assert response.json()["code"] == "WARNING_NOT_FOUND"


def test_get_malformed_warning_id_400(client):
    response = client.get(f"{LIST_URL}/not-a-warning-id", headers=user_headers())
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------- B-API-03 确认 ----------
def test_acknowledge_open_warning(client, monkeypatch):
    """OPEN -> ACKNOWLEDGED。"""
    warning_id = _create_open_warning(client, monkeypatch)

    response = _ack(client, warning_id, expected_version=0, comment="已通知值班工程师")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "ACKNOWLEDGED"
    assert data["acknowledgedBy"] == USER_ID
    assert data["acknowledgedAt"].endswith("Z")
    assert data["version"] == 1
    assert data["linkedOrderId"] is None


def test_acknowledge_linked_warning_keeps_order_link(client):
    """C 已建单后再确认：保留 LINKED_TO_ORDER，同时记录确认人与时间。

    真实链路（docs/06 第 14 节）中 C 收到预警会立即建单，预警几乎瞬间进入
    LINKED_TO_ORDER，因此"已关联工单"必须仍然可以被确认。
    """
    warning_id = _create_warning(client)   # 正常流程 -> LINKED_TO_ORDER, version 1

    response = _ack(client, warning_id, expected_version=1)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "LINKED_TO_ORDER"     # 关联事实优先，不被覆盖
    assert data["linkedOrderId"] == "WO-20260917-0001"
    assert data["acknowledgedBy"] == USER_ID
    assert data["acknowledgedAt"].endswith("Z")
    assert data["version"] == 2


def test_acknowledge_with_stale_version_conflicts(client):
    warning_id = _create_warning(client)
    response = _ack(client, warning_id, expected_version=99)

    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"


def test_acknowledge_twice_conflicts(client):
    warning_id = _create_warning(client)
    first = _ack(client, warning_id, expected_version=1)
    assert first.status_code == 200

    second = _ack(client, warning_id, expected_version=first.json()["version"])
    assert second.status_code == 409
    assert second.json()["code"] == "INVALID_STATE_TRANSITION"


def test_acknowledge_requires_permission(client, monkeypatch):
    warning_id = _create_warning(client)
    monkeypatch.setattr(
        member_d,
        "get_access_context",
        lambda user_id, trace_id: {
            "userId": user_id,
            "permissions": ["WARNING_READ"],
            "enabled": True,
        },
    )
    response = _ack(client, warning_id, expected_version=1)
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_acknowledge_requires_idempotency_key(client):
    warning_id = _create_warning(client)
    response = client.post(
        f"{LIST_URL}/{warning_id}/acknowledgements",
        json={"operatorId": USER_ID, "expectedVersion": 1},
        headers=user_headers(),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_acknowledge_is_idempotent(client):
    warning_id = _create_warning(client)
    key = str(uuid.uuid4())

    first = _ack(client, warning_id, expected_version=1, key=key)
    second = _ack(client, warning_id, expected_version=1, key=key)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.parametrize(
    "mutate,field",
    [
        (lambda b: b.pop("operatorId"), "operatorId"),
        (lambda b: b.__setitem__("operatorId", "bad"), "operatorId"),
        (lambda b: b.pop("expectedVersion"), "expectedVersion"),
        (lambda b: b.__setitem__("expectedVersion", -1), "expectedVersion"),
        (lambda b: b.__setitem__("expectedVersion", "1"), "expectedVersion"),
        (lambda b: b.__setitem__("comment", "x" * 301), "comment"),
        (lambda b: b.__setitem__("unknown", 1), "unknown"),
    ],
)
def test_acknowledgement_field_validation(client, mutate, field):
    warning_id = _create_warning(client)
    body = {"operatorId": USER_ID, "expectedVersion": 1, "comment": None}
    mutate(body)

    response = client.post(
        f"{LIST_URL}/{warning_id}/acknowledgements",
        json=body,
        headers=user_headers(idempotency_key=str(uuid.uuid4())),
    )
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert field in {item["field"] for item in payload["details"]}
