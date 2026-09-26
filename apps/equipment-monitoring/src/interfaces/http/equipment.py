from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.application import equipment_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import trace_id

router = APIRouter(prefix="/api/v1", tags=["C-INT-01 设备查询"])


@router.get("/equipment")
def list_equipment(
    keyword: str | None = Query(default=None, max_length=50),
    productionLineId: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    """A-API-01：分页查询设备（keyword 按设备编号/名称模糊）"""
    from src.domain.models import Equipment

    query = db.query(Equipment)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (Equipment.equipment_id.like(like))
            | (Equipment.name.like(like))
        )
    if productionLineId:
        query = query.filter(
            Equipment.production_line_id == productionLineId
        )
    if status:
        query = query.filter(Equipment.current_status == status)
    total = query.count()
    items = (
        query.order_by(Equipment.equipment_id.asc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return {
        "items": [equipment_service.get_equipment(db, item.equipment_id)
                  for item in items],
        "page": page,
        "pageSize": pageSize,
        "total": total,
        "totalPages": (total + pageSize - 1) // pageSize,
    }


@router.get("/equipment/{equipment_id}")
def get_equipment(
    equipment_id: str,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    return equipment_service.get_equipment(db, equipment_id)
