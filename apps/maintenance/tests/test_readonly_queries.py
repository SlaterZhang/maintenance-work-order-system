"""C-API-08 / C-API-09：备件申请列表与审计日志查询接口测试。

覆盖：鉴权、过滤、分页、契约字段完整性、降序、
以及「审计日志按业务工单号 join 转换」这一关键语义。
"""

import pytest

from src.domain import models
from src.domain.enums import (
    WorkOrderPriority,
    WorkOrderSource,
    WorkOrderStatus,
)
from src.domain.ids import new_order_id, new_spare_part_id

SPARE_URL = "/api/v1/spare-requests"
AUDIT_URL = "/api/v1/audit-logs"

TRACE = "trace-readonly-0001"


def _seed_part(db, on_hand=10, reorder=2) -> models.SparePart:
    part = models.SparePart(
        spare_part_id=new_spare_part_id(),
        name="主轴轴承",
        specification="6208-2RS",
        unit="个",
        on_hand_quantity=on_hand,
        reserved_quantity=0,
        reorder_point=reorder,
    )
    db.add(part)
    db.commit()
    return part


def _seed_order(db, status=WorkOrderStatus.MAINTAINING) -> models.WorkOrder:
    order = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource.WARNING.value,
        warning_id=None,
        equipment_id="EQ-000001",
        equipment_name_snapshot="一号数控机床",
        title="主轴轴承振动异常",
        description="d",
        priority=WorkOrderPriority.P1.value,
        status=status.value,
        reporter_id="system",
    )
    db.add(order)
    db.commit()
    return order


def _create_request(client, order_id: str, part_id: str, qty=2) -> dict:
    """提交备件申请。幂等键含数量，否则同单同件多次申请会被判为键冲突。"""
    response = client.post(
        f"/api/v1/work-orders/{order_id}/spare-requests",
        json={
            "sparePartId": part_id,
            "requestedQuantity": qty,
            "requesterId": "USER-C-001",
            "reason": "维修领用",
        },
        headers={
            "Idempotency-Key": f"idem-{order_id}-{part_id}-{qty}",
            "X-Trace-Id": TRACE,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- C-API-08
def test_spare_list_requires_login(client):
    """清空 Authorization -> 401。"""
    response = client.get(SPARE_URL, headers={"Authorization": ""})
    assert response.status_code == 401, response.text


def test_spare_list_empty_is_well_formed(client):
    """无数据时返回规范空页。"""
    body = client.get(SPARE_URL).json()
    assert body == {
        "items": [], "page": 1, "pageSize": 20, "total": 0, "totalPages": 0,
    }


def test_spare_list_contract_fields(client, db):
    """每条记录含契约 SpareRequest 全部字段。"""
    order = _seed_order(db)
    part = _seed_part(db)
    _create_request(client, order.order_id, part.spare_part_id)

    item = client.get(SPARE_URL).json()["items"][0]
    expected = {
        "requestId", "orderId", "sparePartId", "requestedQuantity",
        "approvedQuantity", "issuedQuantity", "returnedQuantity",
        "status", "requesterId", "approverId", "reason", "version",
        "createdAt", "updatedAt",
    }
    assert expected <= set(item)
    assert item["orderId"] == order.order_id          # 业务工单号，非主键
    assert item["sparePartId"] == part.spare_part_id   # 业务备件编码，非主键
    assert item["status"] == "PENDING_APPROVAL"
    assert item["approverId"] is None


def test_spare_list_filters_by_order_number(client, db):
    """orderId 参数按业务工单号匹配（表内存的是主键外键）。"""
    order_a = _seed_order(db)
    order_b = _seed_order(db)
    part = _seed_part(db)
    _create_request(client, order_a.order_id, part.spare_part_id, qty=2)
    _create_request(client, order_b.order_id, part.spare_part_id, qty=5)

    body = client.get(f"{SPARE_URL}?orderId={order_a.order_id}").json()
    assert body["total"] == 1
    assert body["items"][0]["orderId"] == order_a.order_id
    assert body["items"][0]["requestedQuantity"] == 2


def test_spare_list_filters_by_status_and_part(client, db):
    """status 与 sparePartId 过滤生效。"""
    order = _seed_order(db)
    part_a = _seed_part(db)
    part_b = _seed_part(db)
    _create_request(client, order.order_id, part_a.spare_part_id)
    _create_request(client, order.order_id, part_b.spare_part_id)

    assert client.get(f"{SPARE_URL}?status=PENDING_APPROVAL").json()["total"] == 2
    assert client.get(f"{SPARE_URL}?status=COMPLETED").json()["total"] == 0

    by_part = client.get(f"{SPARE_URL}?sparePartId={part_a.spare_part_id}").json()
    assert by_part["total"] == 1
    assert by_part["items"][0]["sparePartId"] == part_a.spare_part_id


def test_spare_list_pagination(client, db):
    """分页切片正确，total 为全量。"""
    order = _seed_order(db)
    part = _seed_part(db)
    for i in range(3):
        _create_request(client, order.order_id, part.spare_part_id, qty=i + 1)

    page1 = client.get(f"{SPARE_URL}?page=1&pageSize=2").json()
    page2 = client.get(f"{SPARE_URL}?page=2&pageSize=2").json()
    assert page1["total"] == 3 and page1["totalPages"] == 2
    assert len(page1["items"]) == 2 and len(page2["items"]) == 1


# ---------------------------------------------------------------- C-API-09
def test_audit_requires_login(client):
    response = client.get(AUDIT_URL, headers={"Authorization": ""})
    assert response.status_code == 401, response.text


def test_audit_empty_is_well_formed(client):
    body = client.get(AUDIT_URL).json()
    assert body == {
        "items": [], "page": 1, "pageSize": 20, "total": 0, "totalPages": 0,
    }


def test_audit_exposes_business_order_number(client, db):
    """审计条目返回业务工单号，而不是 audit_log.order_id 的整数主键。

    这是本接口最容易被实现错的一点：表内 order_id 是外键主键，
    直接返回会得到 ``1`` 这种对前端无意义的数字。
    """
    order = _seed_order(db)
    db.add(models.AuditLog(
        order_id=order.id,
        action="COMMAND:START",
        operator_id="USER-C-002",
        before_value="PENDING_MAINTENANCE",
        after_value="MAINTAINING",
        detail="开始维修",
        trace_id=TRACE,
    ))
    db.commit()

    item = client.get(AUDIT_URL).json()["items"][0]
    assert item["orderId"] == order.order_id
    assert isinstance(item["orderId"], str)
    assert item["action"] == "COMMAND:START"
    assert item["beforeValue"] == "PENDING_MAINTENANCE"
    assert item["afterValue"] == "MAINTAINING"
    assert item["traceId"] == TRACE
    expected = {"id", "orderId", "action", "operatorId", "beforeValue",
                "afterValue", "detail", "traceId", "createdAt"}
    assert expected <= set(item)


def test_audit_null_order_id_is_preserved(client, db):
    """无关联工单的系统级条目 orderId 为 null，不是 0 或空串。"""
    db.add(models.AuditLog(
        order_id=None, action="AUTO_SYSTEM_TICK",
        operator_id="USER-SYSTEM-AUTO", detail="系统动作",
    ))
    db.commit()

    item = client.get(AUDIT_URL).json()["items"][0]
    assert item["orderId"] is None


def test_audit_filters(client, db):
    """orderId / operatorId / action 模糊匹配过滤。"""
    order_a = _seed_order(db)
    order_b = _seed_order(db)
    db.add_all([
        models.AuditLog(order_id=order_a.id, action="COMMAND:START",
                        operator_id="USER-C-002", trace_id=TRACE),
        models.AuditLog(order_id=order_b.id, action="AUTO_CREATE_FROM_WARNING",
                        operator_id="system"),
    ])
    db.commit()

    assert client.get(f"{AUDIT_URL}?orderId={order_a.order_id}").json()["total"] == 1

    by_operator = client.get(f"{AUDIT_URL}?operatorId=USER-C-002").json()
    assert by_operator["total"] == 1
    assert by_operator["items"][0]["operatorId"] == "USER-C-002"

    by_action = client.get(f"{AUDIT_URL}?action=AUTO_").json()
    assert by_action["total"] == 1
    assert by_action["items"][0]["action"] == "AUTO_CREATE_FROM_WARNING"


def test_audit_descending_and_paged(client, db):
    """按 createdAt 降序；分页切片正确。"""
    for i in range(3):
        db.add(models.AuditLog(
            order_id=None, action=f"STEP_{i}", operator_id="USER-C-002",
        ))
        db.commit()
    page1 = client.get(f"{AUDIT_URL}?page=1&pageSize=2").json()
    page2 = client.get(f"{AUDIT_URL}?page=2&pageSize=2").json()
    assert page1["total"] == 3
    assert page1["items"][0]["action"] == "STEP_2"     # 最新在前
    assert len(page2["items"]) == 1


def test_audit_rejects_bad_paging(client):
    """page=0 / pageSize>100 越界。"""
    assert client.get(f"{AUDIT_URL}?page=0").status_code in (400, 422)
    assert client.get(f"{AUDIT_URL}?pageSize=101").status_code in (400, 422)
