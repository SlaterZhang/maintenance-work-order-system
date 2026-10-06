from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.application import telemetry_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import (
    idempotency_key, internal_token, operator_context, trace_id,
)

router = APIRouter(prefix="/api/v1/equipment", tags=["A-运行数据"])


@router.get("/{equipmentId}/telemetry")
def list_equipment_telemetry(
    equipmentId: str,
    request: Request,
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    """A-API-04：查询设备运行数据（measuredAt 降序，登录身份即可）"""
    operator_context(request, x_trace_id)   # 阶段1鉴权闭合补漏（2026-10-06）
    return telemetry_service.list_telemetry(
        db, equipmentId, from_time, to_time, page, pageSize
    )


@router.post("/{equipmentId}/telemetry", status_code=202)
def ingest_equipment_telemetry(
    equipmentId: str,
    body: dict,
    x_trace_id: str = Depends(trace_id),
    idem: str = Depends(idempotency_key),
    _token: str = Depends(internal_token),
    db: Session = Depends(get_db),
):
    """A-API-05：批量接收设备运行数据（存库，不触发联动）"""
    return telemetry_service.ingest_telemetry(db, equipmentId, body)
