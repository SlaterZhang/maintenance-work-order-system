"""C-INT-02：健康评估入口（``POST /api/v1/health-evaluations``）。

契约：``x-owner-member: MEMBER_B``、``security: internalToken``、
成功 200 且返回 ``HealthEvaluationResponse``。
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.application import evaluation_service
from src.infrastructure.db import get_db
from src.infrastructure.idempotency import IdempotencyContext
from src.interfaces.http.deps import (
    idempotency_key,
    internal_token,
    required_trace_id,
)
from src.interfaces.http.payloads import parse_health_evaluation
from src.domain import models

router = APIRouter(prefix="/api/v1", tags=["B-健康评估"])


@router.post("/health-evaluations")
def evaluate_equipment_health(
    body: dict,
    x_trace_id: str = Depends(required_trace_id),
    _token: str = Depends(internal_token),
    idem_key: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    """对一个监测样本评分；HIGH/CRITICAL 时同步生成 ``WarningId``。"""
    parsed = parse_health_evaluation(body)
    idem = IdempotencyContext(key=idem_key, raw_body=body)

    cached = idem.replay(db)
    if cached is not None:
        return JSONResponse(status_code=cached.http_status, content=cached.body)

    return evaluation_service.evaluate_health(
        db, parsed, x_trace_id, idem=idem
    )


@router.get("/health-evaluations/latest")
def get_latest_health_evaluation(
    equipmentId: str = Query(..., description="设备ID"),
    _token: str = Depends(internal_token),
    db: Session = Depends(get_db),
) -> dict:
    """获取设备的最新健康评估结果"""
    latest = (
        db.query(models.HealthEvaluation)
        .filter(models.HealthEvaluation.equipment_id == equipmentId)
        .order_by(models.HealthEvaluation.evaluated_at.desc())
        .first()
    )
    if latest is None:
        return {
            "equipmentId": equipmentId,
            "hasEvaluation": False,
        }
    return {
        "equipmentId": latest.equipment_id,
        "hasEvaluation": True,
        "healthScore": latest.health_score,
        "riskLevel": latest.risk_level,
        "suspectedFault": latest.suspected_fault,
        "recommendedAction": latest.recommended_action,
        "modelVersion": latest.model_version,
        "evaluatedAt": latest.evaluated_at.isoformat() + "Z",
    }
