from fastapi import APIRouter, Depends, Query, Header, Request
from sqlalchemy.orm import Session

from src.infrastructure.db import get_db
from src.application import work_order_service
from src.interfaces.http.deps import (
    trace_id as get_trace_id, idempotency_key,
)
from src.interfaces.clients.member_d import MemberDClient
from src.domain import models
from src.domain.errors import BadRequestError

router = APIRouter(prefix="/api/v1/work-orders", tags=["C-维修工单"])


def _permissions(request: Request, trace_id: str) -> list[str]:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise BadRequestError("缺少 X-User-Id")
    ctx = MemberDClient.get_access_context(user_id, trace_id) or {}
    return ctx.get("permissions", [])


@router.get("")
def list_work_orders(
    equipmentId: str | None = Query(default=None),
    warningId: str | None = Query(default=None),
    status: str | None = Query(default=None),
    assigneeId: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(get_trace_id),
    db: Session = Depends(get_db),
):
    q = db.query(models.WorkOrder)
    if equipmentId:
        q = q.filter(models.WorkOrder.equipment_id == equipmentId)
    if warningId:
        q = q.filter(models.WorkOrder.warning_id == warningId)
    if status:
        q = q.filter(models.WorkOrder.status == status)
    if assigneeId:
        q = q.filter(models.WorkOrder.assignee_id == assigneeId)
    total = q.count()
    items = (q.order_by(models.WorkOrder.created_at.desc())
             .offset((page - 1) * pageSize).limit(pageSize).all())
    return {
        "items": [work_order_service.serialize_order(o) for o in items],
        "page": page, "pageSize": pageSize, "total": total,
        "totalPages": (total + pageSize - 1) // pageSize,
    }


@router.post("", status_code=201)
def create_manual_work_order(
    body: dict,
    x_trace_id: str = Depends(get_trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """C-API-02：人工报修/巡检工单"""
    from src.infrastructure.idempotency import check_and_store, store_response
    cached = check_and_store(db, idem, body)
    if cached:
        return cached
    result = work_order_service.create_manual_order(db, body, x_trace_id)
    store_response(db, idem, body, result, 201)
    db.commit()
    return result


@router.get("/{orderId}")
def get_work_order(orderId: str,
                   x_trace_id: str = Depends(get_trace_id),
                   db: Session = Depends(get_db)):
    o = work_order_service.get_order(db, orderId)
    return work_order_service.serialize_order(o)


@router.post("/{orderId}/commands")
def execute_work_order_command(
    orderId: str,
    body: dict,
    request: Request,
    x_trace_id: str = Depends(get_trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """C-API-04：执行工单状态命令"""
    from src.infrastructure.idempotency import check_and_store, store_response
    cached = check_and_store(db, idem, body)
    if cached:
        return cached

    perms = _permissions(request, x_trace_id)
    result = work_order_service.execute_command(
        db, orderId, body, x_trace_id, perms
    )
    store_response(db, idem, body, result, 200)
    db.commit()
    return result