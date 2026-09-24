from sqlalchemy.orm import Session
from src.domain import models
from src.domain.enums import SpareRequestAction, SpareRequestStatus
from src.domain.errors import (
    SparePartNotFoundError, SpareRequestNotFoundError,
    InsufficientStockError, ConflictError, BadRequestError,
)
from src.domain.state_machine import transition_spare, SPARE_ACTION_PERMISSION
from src.domain.ids import new_spare_request_id


def _get_request(db: Session, request_id: str) -> models.SpareRequest:
    r = db.query(models.SpareRequest).filter(
        models.SpareRequest.request_id == request_id
    ).first()
    if not r:
        raise SpareRequestNotFoundError()
    return r


def create_spare_request(db: Session, order_id_db: int, body: dict) -> dict:
    part = db.query(models.SparePart).filter(
        models.SparePart.spare_part_id == body["sparePartId"]
    ).first()
    if not part:
        raise SparePartNotFoundError()

    req = models.SpareRequest(
        request_id=new_spare_request_id(),
        order_id=order_id_db,
        spare_part_id=part.id,
        requested_quantity=body["requestedQuantity"],
        status=SpareRequestStatus.PENDING_APPROVAL.value,
        requester_id=body["requesterId"],
        reason=body["reason"],
    )
    db.add(req)
    db.commit()
    return _serialize(req)


def execute_spare_command(db: Session, request_id: str, body: dict,
                          operator_permissions: list[str]) -> dict:
    req = _get_request(db, request_id)
    if body["expectedVersion"] != req.version:
        raise ConflictError("版本冲突")

    action = SpareRequestAction(body["action"])
    perm = SPARE_ACTION_PERMISSION[action]
    if perm not in operator_permissions and "ADMIN_ALL" not in operator_permissions:
        from src.domain.errors import ForbiddenError
        raise ForbiddenError(f"缺少权限 {perm}")

    part = db.query(models.SparePart).get(req.spare_part_id)
    current = SpareRequestStatus(req.status)
    target = transition_spare(current, action)

    if action == SpareRequestAction.APPROVE:
        req.approved_quantity = body.get("quantity", req.requested_quantity)
        req.approver_id = body["operatorId"]

    elif action == SpareRequestAction.RESERVE:
        qty = req.approved_quantity or req.requested_quantity
        if part.available_quantity < qty:
            raise InsufficientStockError(
                f"可用库存 {part.available_quantity} < 需要 {qty}"
            )
        part.reserved_quantity += qty
        part.version += 1
        db.add(models.InventoryTransaction(
            spare_part_id=part.id, request_id=req.id,
            order_id=req.order_id, tx_type="RESERVE",
            quantity=qty, operator_id=body["operatorId"],
        ))

    elif action == SpareRequestAction.ISSUE:
        qty = body.get("quantity")
        if not qty or qty <= 0:
            raise BadRequestError("ISSUE 必须提供正数 quantity")
        if part.on_hand_quantity < qty:
            raise InsufficientStockError("账面库存不足")
        part.on_hand_quantity -= qty
        part.reserved_quantity = max(0, part.reserved_quantity - qty)
        part.version += 1
        req.issued_quantity += qty
        db.add(models.InventoryTransaction(
            spare_part_id=part.id, request_id=req.id,
            order_id=req.order_id, tx_type="ISSUE",
            quantity=qty, operator_id=body["operatorId"],
        ))

    elif action == SpareRequestAction.RETURN:
        qty = body.get("quantity")
        if not qty or qty <= 0:
            raise BadRequestError("RETURN 必须提供正数 quantity")
        part.on_hand_quantity += qty
        part.version += 1
        req.returned_quantity += qty
        db.add(models.InventoryTransaction(
            spare_part_id=part.id, request_id=req.id,
            order_id=req.order_id, tx_type="RETURN",
            quantity=qty, operator_id=body["operatorId"],
        ))

    req.status = target.value
    req.version += 1
    db.commit()
    return _serialize(req)


def _serialize(r: models.SpareRequest) -> dict:
    return {
        "requestId": r.request_id,
        "orderId": r.order.order_id if r.order else None,
        "sparePartId": (
            r.spare_part.spare_part_id if hasattr(r, "spare_part") and r.spare_part
            else None
        ),
        "requestedQuantity": r.requested_quantity,
        "approvedQuantity": r.approved_quantity,
        "issuedQuantity": r.issued_quantity,
        "returnedQuantity": r.returned_quantity,
        "status": r.status,
        "requesterId": r.requester_id,
        "approverId": r.approver_id,
        "reason": r.reason,
        "version": r.version,
        "createdAt": r.created_at.isoformat(),
        "updatedAt": r.updated_at.isoformat(),
    }


def serialize_request(r: models.SpareRequest) -> dict:
    return _serialize(r)