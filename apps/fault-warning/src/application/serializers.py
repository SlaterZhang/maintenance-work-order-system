"""领域对象 -> 契约 DTO 的序列化。

规则（``docs/06`` 第 1 节）
--------------------------
* JSON 字段统一 lower camelCase；
* 时间统一 RFC 3339 UTC；
* ``additionalProperties: false``：**一个字段都不多**；
* 可为空的字段必须**显式返回 null**，不得省略、不得用空字符串替代。
"""

from src.domain.ids import to_rfc3339
from src.domain.models import HealthEvaluation, Warning


def serialize_warning(warning: Warning) -> dict:
    """映射契约 ``Warning`` schema（13 个字段，与契约逐一对应）。"""
    return {
        "warningId": warning.warning_id,
        "equipmentId": warning.equipment_id,
        "riskLevel": warning.risk_level,
        "healthScore": round(float(warning.health_score), 1),
        "suspectedFault": warning.suspected_fault,
        "recommendedAction": warning.recommended_action,
        "status": warning.status,
        "warningAt": to_rfc3339(warning.warning_at),
        "modelVersion": warning.model_version,
        "linkedOrderId": warning.linked_order_id,
        "acknowledgedBy": warning.acknowledged_by,
        "acknowledgedAt": (
            to_rfc3339(warning.acknowledged_at) if warning.acknowledged_at else None
        ),
        "version": warning.version,
    }


def serialize_evaluation(record: HealthEvaluation) -> dict:
    """映射契约 ``HealthEvaluationResponse`` schema（含阶段3趋势外推字段）。"""
    result = {
        "evaluationId": record.evaluation_id,
        "equipmentId": record.equipment_id,
        "healthScore": round(float(record.health_score), 1),
        "riskLevel": record.risk_level,
        "suspectedFault": record.suspected_fault,
        "recommendedAction": record.recommended_action,
        "modelVersion": record.model_version,
        "evaluatedAt": to_rfc3339(record.evaluated_at),
        "warningId": record.warning_id,
    }
    # 趋势字段：旧记录/取不到历史时为 null（契约允许）
    trend = getattr(record, "trend", None) or "UNKNOWN"
    result.update({
        "trend": trend,
        "trendMetric": getattr(record, "trend_metric", None),
        "trendRatePerDay": (
            round(float(record.trend_rate_per_day), 3)
            if getattr(record, "trend_rate_per_day", None) is not None
            else None
        ),
        "predictedDaysToThreshold": getattr(
            record, "predicted_days_to_threshold", None),
        "trendThreshold": getattr(record, "trend_threshold", None),
        "trendSampleCount": getattr(record, "trend_sample_count", None) or 0,
    })
    return result


def warning_page(items: list[Warning], page: int, page_size: int, total: int) -> dict:
    """映射契约 ``WarningPage`` schema。"""
    return {
        "items": [serialize_warning(item) for item in items],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size if page_size else 0,
    }


def event_accepted(trace_id: str, duplicate: bool) -> dict:
    """映射契约 ``EventAcceptedResponse`` schema。"""
    return {"accepted": True, "duplicate": duplicate, "traceId": trace_id}


def evaluation_page(
    items: list[HealthEvaluation], page: int, page_size: int, total: int
) -> dict:
    """映射契约 ``HealthEvaluationPage`` schema（B-API-04）。"""
    return {
        "items": [serialize_evaluation(item) for item in items],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size if page_size else 0,
    }
