"""B 健康评估接口。

* C-INT-02：``POST /api/v1/health-evaluations``（``security: internalToken``，
  契约 ``HealthEvaluationResponse``）。
* 看板辅助：``GET /api/v1/health-evaluations/latest``（登录身份即可），
  返回设备最近一次评估结果，供看板健康状态展示。
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.application import evaluation_service
from src.application.serializers import serialize_evaluation
from src.infrastructure.db import get_db
from src.infrastructure.idempotency import IdempotencyContext
from src.interfaces.http.deps import (
    current_user_id,
    idempotency_key,
    internal_token,
    required_trace_id,
    trace_id,
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
    request: Request = None,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
) -> dict:
    """看板用：设备的最新健康评估结果。

    鉴权口径与 A 服务设备查询一致：仅要求登录身份（``X-User-Id``），
    不加 ``WARNING_READ`` 门禁——看板健康统计对所有角色可见；
    预警明细的权限边界仍由 B-API-01/02（``WARNING_READ``）承担。
    """
    current_user_id(request)
    latest = (
        db.query(models.HealthEvaluation)
        .filter(models.HealthEvaluation.equipment_id == equipmentId)
        .order_by(models.HealthEvaluation.created_at.desc())
        .first()
    )
    if latest is None:
        return {"equipmentId": equipmentId, "hasEvaluation": False}
    result = serialize_evaluation(latest)
    result["hasEvaluation"] = True
    return result
