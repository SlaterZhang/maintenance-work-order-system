"""B-API-01 ~ B-API-03：预警查询与确认。

``docs/06`` 第 13 节要求按**权限码**校验：
``WARNING_READ`` 用于查询，``WARNING_ACKNOWLEDGE`` 用于确认。
"""

import re

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.application import warning_service
from src.domain.enums import RiskLevel, WarningStatus
from src.domain.errors import ValidationError
from src.domain.ids import EQUIPMENT_ID_PATTERN, WARNING_ID_PATTERN
from src.infrastructure.db import get_db
from src.infrastructure.idempotency import IdempotencyContext
from src.interfaces.http.deps import (
    current_user_context,
    idempotency_key,
    require_permission,
    trace_id,
)
from src.interfaces.http.payloads import parse_acknowledgement

router = APIRouter(prefix="/api/v1/warnings", tags=["B-预警"])

_RISK_VALUES = {item.value for item in RiskLevel}
_STATUS_VALUES = {item.value for item in WarningStatus}


def _validate_warning_id(warning_id: str) -> None:
    if not re.fullmatch(WARNING_ID_PATTERN, warning_id or ""):
        raise ValidationError(
            "warningId 格式非法",
            details=[
                {
                    "field": "warningId",
                    "reason": "格式应为 WARN-YYYYMMDD-NNNN，例如 WARN-20260917-0001",
                }
            ],
        )


def _validate_filters(
    equipment_id: str | None, risk_level: str | None, status: str | None
) -> None:
    """查询参数非法时返回 400 ``VALIDATION_ERROR``，不静默返回空列表。"""
    details: list[dict] = []
    if equipment_id is not None and not re.fullmatch(
        EQUIPMENT_ID_PATTERN, equipment_id
    ):
        details.append(
            {"field": "equipmentId", "reason": "格式应为 EQ-[0-9]{6}"}
        )
    if risk_level is not None and risk_level not in _RISK_VALUES:
        details.append(
            {
                "field": "riskLevel",
                "reason": f"必须是 {' / '.join(sorted(_RISK_VALUES))} 之一",
            }
        )
    if status is not None and status not in _STATUS_VALUES:
        details.append(
            {
                "field": "status",
                "reason": f"必须是 {' / '.join(sorted(_STATUS_VALUES))} 之一",
            }
        )
    if details:
        raise ValidationError("查询参数不合法", details=details)


@router.get("")
def list_warnings(
    request: Request,
    equipmentId: str | None = Query(default=None),
    riskLevel: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
) -> dict:
    """B-API-01：分页查询预警，按 ``warningAt`` 降序。"""
    require_permission(current_user_context(request, x_trace_id), "WARNING_READ")
    _validate_filters(equipmentId, riskLevel, status)

    return warning_service.list_warnings(
        db,
        equipment_id=equipmentId,
        risk_level=riskLevel,
        status=status,
        page=page,
        page_size=pageSize,
    )


@router.get("/{warningId}")
def get_warning(
    warningId: str,
    request: Request,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
) -> dict:
    """B-API-02：查询预警详情。"""
    require_permission(current_user_context(request, x_trace_id), "WARNING_READ")
    _validate_warning_id(warningId)

    return warning_service.get_warning_detail(db, warningId)


@router.post("/{warningId}/acknowledgements")
def acknowledge_warning(
    warningId: str,
    body: dict,
    request: Request,
    x_trace_id: str = Depends(trace_id),
    idem_key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    """B-API-03：确认预警（``OPEN -> ACKNOWLEDGED``）。"""
    require_permission(
        current_user_context(request, x_trace_id), "WARNING_ACKNOWLEDGE"
    )
    _validate_warning_id(warningId)

    parsed = parse_acknowledgement(body)
    idem = IdempotencyContext(key=idem_key, raw_body=body)

    cached = idem.replay(db)
    if cached is not None:
        return JSONResponse(status_code=cached.http_status, content=cached.body)

    return warning_service.acknowledge_warning(
        db, warningId, parsed, x_trace_id, idem=idem
    )
