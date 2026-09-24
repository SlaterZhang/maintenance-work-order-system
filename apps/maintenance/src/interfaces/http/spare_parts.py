from fastapi import APIRouter, Depends, Query, Header, Request
from sqlalchemy.orm import Session

from src.infrastructure.db import get_db
from src.application import spare_service, work_order_service
from src.interfaces.http.deps import (
    trace_id as get_trace_id, idempotency_key,
)
from src.interfaces.clients.member_d import MemberDClient
from src.domain import models
from src.domain.errors import BadRequestError

router = APIRouter(prefix="/api/v1", tags=["C-备件"])


def _permissions(request: Request, trace_id: str) -> list[str]:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise BadRequestError("缺少 X-User-Id")
    ctx = MemberDClient.get_access_context(user_id, trace_id) or {}
    return ctx.get("permissions", [])


@router.get("/spare-parts")
def list_spare_parts(
    keyword: str | None = Query(default=None, max_length=50),
    lowStockOnly: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """C-API-05：分页查询备件"""
    q = db.query(models.SparePart)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (models.SparePart.name.like(like)) |
            (models.SparePart.specification.like(like)) |
            (models.SparePart.spare_part_id.like(like))
        )
    items = q.all()
    if lowStockOnly:
        items = [p for p in items
                 if p.available_quantity <= p.reorder_point]
    total = len(items)
    items = items[(page - 1) * pageSize: (page - 1) * pageSize + pageSize]
    return {
        "items": [{
            "sparePartId": p.spare_part_id,
            "name": p.name,
            "specification": p.specification,
            "unit": p.unit,
            "onHandQuantity": p.on_hand_quantity,
            "reservedQuantity": p.reserved_quantity,
            "availableQuantity": p.available_quantity,
            "reorderPoint": p.reorder_point,
            "version": p.version,
        } for p in items],
        "page": page, "pageSize": pageSize, "total": total,
        "totalPages": (total + pageSize - 1) // pageSize,
    }


@router.post("/work-orders/{orderId}/spare-requests", status_code=201)
def create_spare_request(
    orderId: str, body: dict,
    x_trace_id: str = Depends(get_trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """C-API-06：为工单提交备件申请"""
    from src.infrastructure.idempotency import check_and_store, store_response
    cached = check_and_store(db, idem, body)
    if cached:
        return cached

    order = work_order_service.get_order(db, orderId)
    result = spare_service.create_spare_request(db, order.id, body)
    store_response(db, idem, body, result, 201)
    db.commit()
    return result


@router.post("/spare-requests/{requestId}/commands")
def execute_spare_command(
    requestId: str, body: dict, request: Request,
    x_trace_id: str = Depends(get_trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """C-API-07：审批/预留/领用/退回/关闭/取消"""
    from src.infrastructure.idempotency import check_and_store, store_response
    cached = check_and_store(db, idem, body)
    if cached:
        return cached

    perms = _permissions(request, x_trace_id)
    result = spare_service.execute_spare_command(db, requestId, body, perms)
    store_response(db, idem, body, result, 200)
    db.commit()
    return result