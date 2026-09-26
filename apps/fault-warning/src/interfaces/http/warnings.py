from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.application import warning_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import idempotency_key, trace_id

router = APIRouter(prefix="/api/v1/warnings", tags=["B-API 预警查询"])


@router.get("")
def list_warnings(
    equipmentId: str | None = Query(default=None, max_length=16),
    riskLevel: str | None = Query(default=None, max_length=16),
    status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    """B-API-01：分页查询故障预警（warningAt 降序）"""
    return warning_service.list_warnings(
        db, equipmentId, riskLevel, status, page, pageSize
    )


@router.get("/{warningId}")
def get_warning(
    warningId: str,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    """B-API-02：查询预警详情"""
    return warning_service.get_warning(db, warningId)


@router.post("/{warningId}/acknowledgements")
def acknowledge_warning(
    warningId: str,
    body: dict,
    x_trace_id: str = Depends(trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """B-API-03：确认预警（OPEN → ACKNOWLEDGED）"""
    return warning_service.acknowledge_warning(db, warningId, body)
