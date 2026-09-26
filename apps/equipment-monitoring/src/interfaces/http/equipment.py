from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.application import equipment_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import trace_id

router = APIRouter(prefix="/api/v1", tags=["C-INT-01 设备查询"])


@router.get("/equipment/{equipment_id}")
def get_equipment(
    equipment_id: str,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    return equipment_service.get_equipment(db, equipment_id)
