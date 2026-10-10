from fastapi import APIRouter, Depends, Query, Header, Request
from sqlalchemy.orm import Session

from src.infrastructure.db import get_db
from src.application import spare_service, work_order_service
from src.interfaces.http.deps import (
    trace_id as get_trace_id, idempotency_key,
    operator_context, require_permission,
)
from src.domain import models
from src.domain.errors import BadRequestError

router = APIRouter(prefix="/api/v1", tags=["C-备件"])


@router.get("/spare-parts")
def list_spare_parts(
    request: Request,
    keyword: str | None = Query(default=None, max_length=50),
    lowStockOnly: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(get_trace_id),
    db: Session = Depends(get_db),
):
    """C-API-05：分页查询备件（登录身份即可）"""
    operator_context(request, x_trace_id)
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


@router.get("/spare-requests")
def list_spare_requests(
    request: Request,
    status: str | None = Query(default=None, max_length=30),
    orderId: str | None = Query(default=None, max_length=60),
    sparePartId: str | None = Query(default=None, max_length=60),
    requesterId: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(get_trace_id),
    db: Session = Depends(get_db),
):
    """C-API-08：分页查询备件申请（登录身份即可）"""
    operator_context(request, x_trace_id)
    return spare_service.list_spare_requests(
        db,
        status=status,
        order_id=orderId,
        spare_part_id=sparePartId,
        requester_id=requesterId,
        page=page,
        page_size=pageSize,
    )


@router.post("/work-orders/{orderId}/spare-requests", status_code=201)
def create_spare_request(
    orderId: str, body: dict, request: Request,
    x_trace_id: str = Depends(get_trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """C-API-06：为工单提交备件申请（需 SPARE_REQUEST）"""
    from src.infrastructure.idempotency import check_and_store, store_response
    ctx = operator_context(request, x_trace_id)
    require_permission("SPARE_REQUEST", ctx.get("permissions", []))
    body["operatorId"] = ctx["userId"]      # 服务端权威身份（先覆写再算幂等指纹）
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
    """C-API-07：审批/预留/领用/退回/关闭/取消

    操作人以 D 验签的 JWT 身份为准（服务端覆写 ``body.operatorId``）。
    """
    from src.infrastructure.idempotency import check_and_store, store_response
    ctx = operator_context(request, x_trace_id)
    body["operatorId"] = ctx["userId"]      # 服务端权威身份（先覆写再算幂等指纹）
    cached = check_and_store(db, idem, body)
    if cached:
        return cached

    perms = ctx.get("permissions", [])
    result = spare_service.execute_spare_command(db, requestId, body, perms)
    store_response(db, idem, body, result, 200)
    db.commit()
    return result