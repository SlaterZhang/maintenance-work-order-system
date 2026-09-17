"""备件流程：申请 -> 审批 -> 预留 -> 领用 -> 退回 -> 关闭"""
import pytest

from src.domain import models
from src.domain.ids import new_spare_part_id


USER_HEADERS = {
    "X-User-Id": "USER-C-001",
    "X-Trace-Id": "trace-sp-0001",
}


def _seed_part(db, on_hand=10, reorder=2) -> models.SparePart:
    p = models.SparePart(
        spare_part_id=new_spare_part_id(),
        name="轴承",
        specification="SKF-6204",
        unit="个",
        on_hand_quantity=on_hand,
        reserved_quantity=0,
        reorder_point=reorder,
    )
    db.add(p)
    db.commit()
    return p


def _seed_order(db) -> models.WorkOrder:
    from src.domain.enums import (
        WorkOrderStatus, WorkOrderSource, WorkOrderPriority,
    )
    from src.domain.ids import new_order_id
    o = models.WorkOrder(
        order_id=new_order_id(),
        source_type=WorkOrderSource.MANUAL.value,
        warning_id=None,
        equipment_id="EQ-000001",
        equipment_name_snapshot="设备",
        title="t", description="d",
        priority=WorkOrderPriority.P3.value,
        status=WorkOrderStatus.MAINTAINING.value,
        reporter_id="USER-C-001",
    )
    db.add(o)
    db.commit()
    return o


def _create_request(client, order_id, part_id, qty=2):
    body = {
        "sparePartId": part_id,
        "requestedQuantity": qty,
        "requesterId": "USER-C-001",
        "reason": "更换轴承",
    }
    return client.post(
        f"/api/v1/work-orders/{order_id}/spare-requests",
        json=body,
        headers={**USER_HEADERS, "Idempotency-Key": f"req-{order_id}-{part_id}"},
    )


def _cmd(client, request_id, action, expected_version=0, **extra):
    body = {"action": action, "operatorId": "USER-C-001",
            "expectedVersion": expected_version, **extra}
    return client.post(
        f"/api/v1/spare-requests/{request_id}/commands",
        json=body,
        headers={
            **USER_HEADERS,
            "Idempotency-Key": f"cmd-{request_id}-{action}-{expected_version}",
        },
    )


# ---------- 查询备件 ----------
def test_list_spare_parts(client, db, mock_permissions):
    _seed_part(db, on_hand=10)
    _seed_part(db, on_hand=1, reorder=5)
    r = client.get("/api/v1/spare-parts", headers=USER_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["availableQuantity"] == (
            item["onHandQuantity"] - item["reservedQuantity"]
        )


def test_list_spare_parts_low_stock_only(client, db, mock_permissions):
    _seed_part(db, on_hand=10, reorder=2)
    _seed_part(db, on_hand=1, reorder=5)  # 低库存
    r = client.get("/api/v1/spare-parts?lowStockOnly=true",
                   headers=USER_HEADERS)
    assert r.json()["total"] == 1


def test_list_spare_parts_keyword(client, db, mock_permissions):
    _seed_part(db)
    r = client.get("/api/v1/spare-parts?keyword=轴承", headers=USER_HEADERS)
    assert r.json()["total"] == 1


# ---------- 申请 ----------
def test_create_spare_request(client, db, mock_permissions):
    part = _seed_part(db)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=2)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "PENDING_APPROVAL"
    assert body["requestedQuantity"] == 2
    assert body["requestId"].startswith("SPR-")


def test_create_spare_request_unknown_part(client, db, mock_permissions):
    order = _seed_order(db)
    r = _create_request(client, order.order_id, "SP-999999", qty=1)
    assert r.status_code == 404
    assert r.json()["code"] == "SPARE_PART_NOT_FOUND"


# ---------- 完整流程 ----------
def test_full_spare_lifecycle(client, db, mock_permissions):
    part = _seed_part(db, on_hand=10)
    order = _seed_order(db)

    r = _create_request(client, order.order_id, part.spare_part_id, qty=3)
    rid = r.json()["requestId"]

    # 审批
    r = _cmd(client, rid, "APPROVE", expected_version=0, quantity=3)
    assert r.json()["status"] == "APPROVED"
    assert r.json()["approvedQuantity"] == 3
    assert r.json()["version"] == 1

    # 预留
    r = _cmd(client, rid, "RESERVE", expected_version=1)
    assert r.json()["status"] == "RESERVED"
    db.refresh(part)
    assert part.reserved_quantity == 3
    assert part.available_quantity == 7

    # 领用
    r = _cmd(client, rid, "ISSUE", expected_version=2, quantity=3)
    assert r.json()["status"] == "ISSUED"
    assert r.json()["issuedQuantity"] == 3
    db.refresh(part)
    assert part.on_hand_quantity == 7
    assert part.reserved_quantity == 0

    # 退回 1 件
    r = _cmd(client, rid, "RETURN", expected_version=3, quantity=1)
    assert r.json()["status"] == "PARTIALLY_RETURNED"
    db.refresh(part)
    assert part.on_hand_quantity == 8

    # 关闭
    r = _cmd(client, rid, "CLOSE", expected_version=4)
    assert r.json()["status"] == "CLOSED"


# ---------- 库存非负 ----------
def test_reserve_insufficient_stock_409(client, db, mock_permissions):
    part = _seed_part(db, on_hand=1)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=5)
    rid = r.json()["requestId"]
    _cmd(client, rid, "APPROVE", expected_version=0, quantity=5)
    r = _cmd(client, rid, "RESERVE", expected_version=1)
    assert r.status_code == 409
    assert r.json()["code"] == "INSUFFICIENT_STOCK"
    db.refresh(part)
    assert part.reserved_quantity == 0  # 未变化


def test_issue_insufficient_on_hand_409(client, db, mock_permissions):
    part = _seed_part(db, on_hand=3)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=2)
    rid = r.json()["requestId"]
    _cmd(client, rid, "APPROVE", expected_version=0, quantity=2)
    _cmd(client, rid, "RESERVE", expected_version=1)
    # 手工把 on_hand 降到 1，模拟账实不符
    part.on_hand_quantity = 1
    db.commit()
    r = _cmd(client, rid, "ISSUE", expected_version=2, quantity=2)
    assert r.status_code == 409
    assert r.json()["code"] == "INSUFFICIENT_STOCK"


# ---------- 幂等 ----------
def test_spare_request_idempotent(client, db, mock_permissions):
    part = _seed_part(db)
    order = _seed_order(db)
    body = {
        "sparePartId": part.spare_part_id,
        "requestedQuantity": 1,
        "requesterId": "USER-C-001",
        "reason": "x",
    }
    headers = {**USER_HEADERS, "Idempotency-Key": "sp-req-same"}
    r1 = client.post(f"/api/v1/work-orders/{order.order_id}/spare-requests",
                     json=body, headers=headers)
    r2 = client.post(f"/api/v1/work-orders/{order.order_id}/spare-requests",
                     json=body, headers=headers)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["requestId"] == r2.json()["requestId"]
    assert db.query(models.SpareRequest).count() == 1


# ---------- 非法迁移 ----------
def test_issue_before_reserve_409(client, db, mock_permissions):
    part = _seed_part(db)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=1)
    rid = r.json()["requestId"]
    _cmd(client, rid, "APPROVE", expected_version=0, quantity=1)
    # 未 RESERVE 直接 ISSUE
    r = _cmd(client, rid, "ISSUE", expected_version=1, quantity=1)
    assert r.status_code == 409
    assert r.json()["code"] == "INVALID_STATE_TRANSITION"


# ---------- 取消 ----------
def test_cancel_request_releases_reservation(client, db, mock_permissions):
    part = _seed_part(db, on_hand=10)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=2)
    rid = r.json()["requestId"]
    _cmd(client, rid, "APPROVE", expected_version=0, quantity=2)
    _cmd(client, rid, "RESERVE", expected_version=1)
    db.refresh(part)
    assert part.reserved_quantity == 2

    r = _cmd(client, rid, "CANCEL", expected_version=2, comment="重复申请")
    assert r.json()["status"] == "CANCELLED"


# ---------- 库存流水 ----------
def test_inventory_transactions_recorded(client, db, mock_permissions):
    part = _seed_part(db, on_hand=10)
    order = _seed_order(db)
    r = _create_request(client, order.order_id, part.spare_part_id, qty=2)
    rid = r.json()["requestId"]
    _cmd(client, rid, "APPROVE", expected_version=0, quantity=2)
    _cmd(client, rid, "RESERVE", expected_version=1)
    _cmd(client, rid, "ISSUE", expected_version=2, quantity=2)

    txs = db.query(models.InventoryTransaction).all()
    types = [t.tx_type for t in txs]
    assert types == ["RESERVE", "ISSUE"]