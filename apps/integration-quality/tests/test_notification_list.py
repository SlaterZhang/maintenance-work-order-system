"""D-API-04 通知任务列表查询接口测试。

覆盖：鉴权口径（登录身份 vs 内部令牌）、payload 解析、过滤、分页、契约字段。
"""

import uuid

from src.config import settings

LIST_PATH = "/api/v1/notifications"
POST_PATH = "/api/v1/notifications"
PASSWORD = settings.login_default_password
INTERNAL_TOKEN = settings.internal_api_token


def _token(client, username="USER-D-001") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
        headers={"X-Trace-Id": "trace-d-notify-0001"},
    )
    assert response.status_code == 200, response.text
    return response.json()["accessToken"]


def _bearer(client, username="USER-D-001") -> dict:
    return {
        "Authorization": f"Bearer {_token(client, username)}",
        "X-Trace-Id": "trace-d-notify-0001",
    }


def _submit(client, **overrides) -> dict:
    request = {
        "recipientUserIds": ["USER-C-002"],
        "templateCode": "WORK_ORDER_ASSIGNED",
        "channel": "IN_APP",
        "variables": {"orderId": "WO-20260917-0001"},
        "businessReference": "WO-20260917-0001",
    }
    request.update(overrides)
    response = client.post(
        POST_PATH,
        json=request,
        headers={
            "X-Internal-Token": INTERNAL_TOKEN,
            "X-Trace-Id": "trace-d-notify-0001",
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


# ------------------------------------------------------------------ 鉴权口径
def test_requires_login_identity(client):
    """无 Authorization -> 401（与 POST 的内部令牌口径不同）。"""
    response = client.get(LIST_PATH)
    assert response.status_code == 401, response.text


def test_internal_token_alone_is_not_enough(client):
    """只带 X-Internal-Token 不够：查询是运营人员需求，必须登录身份。"""
    response = client.get(
        LIST_PATH,
        headers={"X-Internal-Token": INTERNAL_TOKEN,
                 "X-Trace-Id": "trace-d-notify-0001"},
    )
    assert response.status_code == 401, response.text


def test_any_logged_in_role_can_read(client):
    """普通角色（非管理员）同样可读通知列表。"""
    _submit(client)
    response = client.get(LIST_PATH, headers=_bearer(client, "USER-C-002"))
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


# ------------------------------------------------------------------ 数据形状
def test_empty_is_well_formed(client):
    body = client.get(LIST_PATH, headers=_bearer(client)).json()
    assert body == {
        "items": [], "page": 1, "pageSize": 20, "total": 0, "totalPages": 0,
    }


def test_payload_is_parsed_into_structured_fields(client):
    """``payload`` 是落库的 JSON 字符串，返回时必须已解析为结构化字段。"""
    created = _submit(client)
    item = client.get(LIST_PATH, headers=_bearer(client)).json()["items"][0]

    assert item["notificationId"] == created["notificationId"]
    assert item["recipientUserIds"] == ["USER-C-002"]
    assert item["templateCode"] == "WORK_ORDER_ASSIGNED"
    assert item["channel"] == "IN_APP"
    assert item["variables"] == {"orderId": "WO-20260917-0001"}
    assert item["businessReference"] == "WO-20260917-0001"
    assert item["traceId"] == "trace-d-notify-0001"

    expected = {"notificationId", "idempotencyKey", "recipientUserIds",
                "templateCode", "channel", "variables", "businessReference",
                "traceId", "createdAt"}
    assert expected <= set(item)


def test_filters_by_recipient(client):
    """recipientUserId 过滤只看该接收人的通知。"""
    _submit(client, recipientUserIds=["USER-C-002"])
    _submit(client, recipientUserIds=["USER-C-003"])

    body = client.get(
        f"{LIST_PATH}?recipientUserId=USER-C-003", headers=_bearer(client)
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["recipientUserIds"] == ["USER-C-003"]


def test_filters_by_template_and_channel(client):
    """templateCode 过滤生效；channel 过滤同样生效。

    注意 templateCode 有白名单（见 domain/enums.py 的 TEMPLATE_CODES），
    只能取 WARNING_CREATED / WORK_ORDER_CREATED / WORK_ORDER_ASSIGNED /
    WORK_ORDER_STATUS_CHANGED / SPARE_REQUEST_PENDING 五个值之一。
    """
    _submit(client, templateCode="WORK_ORDER_ASSIGNED")
    _submit(client, templateCode="WARNING_CREATED")

    by_template = client.get(
        f"{LIST_PATH}?templateCode=WARNING_CREATED", headers=_bearer(client)
    ).json()
    assert by_template["total"] == 1
    assert by_template["items"][0]["templateCode"] == "WARNING_CREATED"

    by_channel = client.get(
        f"{LIST_PATH}?channel=IN_APP", headers=_bearer(client)
    ).json()
    assert by_channel["total"] == 2

    assert client.get(
        f"{LIST_PATH}?channel=SMS", headers=_bearer(client)
    ).json()["total"] == 0


def test_descending_and_paged(client):
    for _ in range(3):
        _submit(client)
    page1 = client.get(
        f"{LIST_PATH}?page=1&pageSize=2", headers=_bearer(client)
    ).json()
    page2 = client.get(
        f"{LIST_PATH}?page=2&pageSize=2", headers=_bearer(client)
    ).json()
    assert page1["total"] == 3 and page1["totalPages"] == 2
    assert len(page1["items"]) == 2 and len(page2["items"]) == 1


def test_rejects_bad_paging(client):
    headers = _bearer(client)
    assert client.get(f"{LIST_PATH}?page=0", headers=headers).status_code in (400, 422)
    assert client.get(
        f"{LIST_PATH}?pageSize=101", headers=headers
    ).status_code in (400, 422)
