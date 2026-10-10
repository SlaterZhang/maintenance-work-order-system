"""C-INT-02：健康评估用例。

一次评估的完整顺序（``docs/06`` 第 14 节第 2~4 步）
--------------------------------------------------
1. ``evaluationId`` 天然幂等：重复提交直接返回首次结果；
2. 向 A 查询设备权威档案，设备不存在 -> 404 ``EQUIPMENT_NOT_FOUND``；
3. 用规则引擎评分，按契约分段得到风险等级；
4. HIGH / CRITICAL 时分配 ``WarningId``；
5. 在**同一事务**内落库：评估记录 + 预警 + outbox 待发送事件 + 幂等记录；
6. 提交之后才尝试向 C 投递 ``WarningRaised``；
   投递失败不回滚已成立的预警，保留 PENDING 供重试。

``WarningId`` 去重
------------------
同一设备 + 同一疑似故障，且预警仍在跟踪（OPEN / ACKNOWLEDGED /
LINKED_TO_ORDER）时**复用**原 ``WarningId``，不重复建预警、不重复发事件。
这是"同一设备同一预警重复评估不产生重复 WarningId"的落点。
"""

import json
import uuid

from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import Session

from src.application import event_dispatch
from src.application import warning_service
from src.application.serializers import evaluation_page, serialize_evaluation
from src.config import settings
from src.domain import models, scoring
from src.domain.enums import (
    ACTIONABLE_RISK_LEVELS,
    ACTIVE_WARNING_STATUSES,
    OutboxEventType,
    RiskLevel,
    SYSTEM_OPERATOR_ID,
    WarningStatus,
)
from src.domain.errors import EquipmentNotFoundError, InternalError
from src.domain import trend as trend_engine
from src.domain.ids import (
    WARNING_ID_SEQUENCE_MAX,
    format_warning_id,
    parse_rfc3339,
    to_rfc3339,
    utc_day,
    utc_now,
)
from src.infrastructure import outbox
from src.infrastructure.idempotency import IdempotencyContext
from src.interfaces.clients import member_a

SCHEMA_VERSION = "2.0"
SOURCE_MEMBER = "MEMBER_B"


def _safe_recent_telemetry(equipment_id: str, trace_id: str) -> list | None:
    """取 A 的最近遥测；任何失败返回 None（趋势优雅降级为 UNKNOWN）。"""
    try:
        return member_a.fetch_recent_telemetry(equipment_id, trace_id)
    except Exception:  # noqa: BLE001 - 趋势绝不阻塞评估主链路
        return None


def evaluate_health(
    db: Session,
    body: dict,
    trace_id: str,
    idem: IdempotencyContext | None = None,
) -> dict:
    """执行一次健康评估并返回契约 ``HealthEvaluationResponse``。

    阶段3：评分后基于 A 的历史遥测做退化趋势外推，随评估留档返回
    （``trend`` / ``predictedDaysToThreshold`` 等字段见 ``domain/trend.py``）。
    """
    existing = (
        db.query(models.HealthEvaluation)
        .filter(models.HealthEvaluation.evaluation_id == body["evaluationId"])
        .first()
    )
    if existing is not None:
        result = serialize_evaluation(existing)
        if idem is not None:
            idem.remember(db, result, 200)
        db.commit()
        return result

    equipment = member_a.get_equipment(body["equipmentId"], trace_id)
    if equipment is None:
        raise EquipmentNotFoundError(f"设备 {body['equipmentId']} 不存在")

    health = scoring.evaluate_sample(body["sample"])
    requested_at = parse_rfc3339(body["requestedAt"])
    evaluated_at = utc_now()

    trend = trend_engine.analyze_trend(
        _safe_recent_telemetry(body["equipmentId"], trace_id))

    warning, created = _obtain_warning(
        db, body, health, requested_at, evaluated_at
    )

    if health.risk_level is RiskLevel.LOW:
        _auto_resolve_on_recovery(
            db,
            body["equipmentId"],
            body["evaluationId"],
            health.health_score,
            trace_id,
            evaluated_at,
        )

    record = models.HealthEvaluation(
        evaluation_id=body["evaluationId"],
        equipment_id=body["equipmentId"],
        health_score=health.health_score,
        risk_level=health.risk_level.value,
        suspected_fault=health.suspected_fault,
        recommended_action=health.recommended_action,
        model_version=health.model_version,
        evaluated_at=evaluated_at,
        requested_at=requested_at,
        warning_id=warning.warning_id if warning is not None else None,
        trend=trend["trend"],
        trend_metric=trend["trendMetric"],
        trend_rate_per_day=trend["trendRatePerDay"],
        predicted_days_to_threshold=trend["predictedDaysToThreshold"],
        trend_threshold=trend["trendThreshold"],
        trend_sample_count=trend["trendSampleCount"],
        sample_json=json.dumps(body["sample"], ensure_ascii=False),
        trace_id=trace_id,
    )
    db.add(record)

    if warning is not None and created:
        _enqueue_warning_raised(
            db, warning, body["sample"], trace_id, evaluated_at
        )

    result = serialize_evaluation(record)
    if idem is not None:
        idem.remember(db, result, 200)
    db.commit()

    # 业务已经成立：提交之后才投递，失败不影响预警本身
    event_dispatch.dispatch_pending_events(db)
    return result


def list_evaluations(
    db: Session,
    *,
    equipment_id: str | None = None,
    risk_level: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """B-API-04：分页查询健康评估历史，按 ``evaluatedAt`` 降序（``id`` 作稳定次序）。"""
    query = db.query(models.HealthEvaluation)
    if equipment_id:
        query = query.filter(
            models.HealthEvaluation.equipment_id == equipment_id)
    if risk_level:
        query = query.filter(models.HealthEvaluation.risk_level == risk_level)

    total = query.count()
    items = (
        query.order_by(
            models.HealthEvaluation.evaluated_at.desc(),
            models.HealthEvaluation.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return evaluation_page(items, page, page_size, total)


def _obtain_warning(
    db: Session,
    body: dict,
    health: scoring.HealthResult,    requested_at,
    evaluated_at,
) -> tuple[models.Warning | None, bool]:
    """返回 ``(预警, 是否新建)``；非 HIGH/CRITICAL 返回 ``(None, False)``。"""
    if health.risk_level not in ACTIONABLE_RISK_LEVELS:
        return None, False

    active_statuses = [status.value for status in ACTIVE_WARNING_STATUSES]
    existing = (
        db.query(models.Warning)
        .filter(
            models.Warning.equipment_id == body["equipmentId"],
            models.Warning.suspected_fault == health.suspected_fault,
            models.Warning.status.in_(active_statuses),
        )
        .order_by(models.Warning.id.desc())
        .first()
    )
    if existing is not None:
        return existing, False

    day = utc_day(evaluated_at)
    for _ in range(settings.warning_id_max_attempts):
        warning = models.Warning(
            warning_id=_allocate_warning_id(db, day),
            equipment_id=body["equipmentId"],
            risk_level=health.risk_level.value,
            health_score=health.health_score,
            suspected_fault=health.suspected_fault,
            recommended_action=health.recommended_action,
            status=WarningStatus.OPEN.value,
            warning_at=requested_at,
            model_version=health.model_version,
            version=0,
        )
        try:
            # SAVEPOINT：唯一约束冲突只回滚这一次尝试，不影响外层事务
            with db.begin_nested():
                db.add(warning)
                db.flush()
            return warning, True
        except IntegrityError:
            _safe_expunge(db, warning)
            continue

    raise InternalError("当日 WarningId 序号分配失败，请稍后重试")


def _allocate_warning_id(db: Session, day: str) -> str:
    """取当日已用最大序号 +1。

    不使用随机数：随机数在批量评估下会碰撞，而 ``warning_id`` 有唯一约束，
    碰撞会把一次评估变成 500。
    """
    prefix = f"WARN-{day}-"
    latest = (
        db.query(models.Warning.warning_id)
        .filter(models.Warning.warning_id.like(f"{prefix}%"))
        .order_by(models.Warning.warning_id.desc())
        .first()
    )
    next_sequence = 1
    if latest is not None:
        next_sequence = int(latest[0].rsplit("-", 1)[1]) + 1
    if next_sequence > WARNING_ID_SEQUENCE_MAX:
        raise InternalError(f"{day} 当日的预警序号已用尽（上限 {WARNING_ID_SEQUENCE_MAX}）")
    return format_warning_id(day, next_sequence)


def _safe_expunge(db: Session, instance) -> None:
    try:
        db.expunge(instance)
    except InvalidRequestError:
        pass


def _auto_resolve_on_recovery(
    db: Session,
    equipment_id: str,
    evaluation_id: str,
    recovery_score: float,
    trace_id: str,
    evaluated_at,
) -> list[models.Warning]:
    """设备恢复（最新评估 LOW）时闭环该设备全部活跃预警。

    2026-10-07 新增（C-INT-09）：修复"恢复正常数据后预警卡片常驻"。
    此前 ``_obtain_warning`` 在非 HIGH/CRITICAL 时直接 ``return None``，
    LOW 评估落库却完全不碰已有预警，预警永久悬在 ``LINKED_TO_ORDER``。

    每条被闭环的预警都会登记一条 ``WarningResolvedReported`` outbox，
    与预警状态在同一事务提交，投递失败保留 PENDING 供重试；C 收到后
    结掉仍停在早期状态、从未进入维修的关联工单。

    :param recovery_score: 本次恢复评估的健康分。闭环事件必须回报
        **这次**证明恢复的健康分，而不是预警当初的风险分
        （预警记录上的 ``health_score`` 是 49.4 这类异常分）。
    :returns: 本次真正闭环（活跃态 → RESOLVED）的预警列表。
    """
    resolved: list[models.Warning] = []
    for warning in warning_service.active_warnings_for_equipment(db, equipment_id):
        was_active = (
            WarningStatus(warning.status) in ACTIVE_WARNING_STATUSES
        )
        changed = warning_service.auto_resolve_warning(
            db,
            warning,
            trigger=(
                f"设备 {equipment_id} 最新健康评估为 LOW（evaluationId="
                f"{evaluation_id}），遥测证明已恢复正常，自动闭环预警 "
                f"{warning.warning_id}"
            ),
            trace_id=trace_id,
            operator_id=SYSTEM_OPERATOR_ID,
        )
        if changed and was_active:
            resolved.append(warning)
            _enqueue_warning_resolved(
                db, warning, recovery_score, trace_id, evaluated_at
            )
    return resolved


def _enqueue_warning_resolved(
    db: Session,
    warning: models.Warning,
    recovery_score: float,
    trace_id: str,
    occurred_at,
) -> models.OutboxEvent:
    """登记 ``WarningResolvedReported`` 待发送事件（与业务记录同事务提交）。"""
    event = build_warning_resolved_event(
        warning, recovery_score, trace_id, occurred_at
    )
    return outbox.enqueue(
        db,
        event_id=event["eventId"],
        event_type=OutboxEventType.WARNING_RESOLVED,
        target_url=f"{settings.maintenance_service_url}"
        "/api/v1/integration/warning-closures",
        payload=event,
        trace_id=trace_id,
    )


def build_warning_resolved_event(
    warning: models.Warning,
    recovery_score: float,
    trace_id: str,
    occurred_at,
) -> dict:
    """构造契约 ``WarningResolvedEvent`` 报文（C-INT-09）。

    ``payload.healthScore`` 是**恢复评估**的健康分（证明设备已正常），
    不是预警当初触发时的风险分。
    """
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": "WarningResolvedReported",
        "schemaVersion": SCHEMA_VERSION,
        "occurredAt": to_rfc3339(occurred_at),
        "sourceMember": SOURCE_MEMBER,
        "traceId": trace_id,
        "payload": {
            "warningId": warning.warning_id,
            "equipmentId": warning.equipment_id,
            "healthScore": round(float(recovery_score), 1),
            "resolvedAt": to_rfc3339(occurred_at),
            "resolvedBy": SYSTEM_OPERATOR_ID,
            "reason": "设备遥测恢复正常（健康评估 LOW），预警自动闭环",
            "linkedOrderId": warning.linked_order_id,
        },
    }


def _enqueue_warning_raised(
    db: Session,
    warning: models.Warning,
    sample: dict,
    trace_id: str,
    evaluated_at,
) -> models.OutboxEvent:
    """登记 ``WarningRaised`` 待发送事件（与业务记录同事务提交）。"""
    event = build_warning_raised_event(warning, sample, trace_id, evaluated_at)
    row = outbox.enqueue(
        db,
        event_id=event["eventId"],
        event_type=OutboxEventType.WARNING_RAISED,
        target_url=f"{settings.maintenance_service_url}"
        "/api/v1/integration/warning-events",
        payload=event,
        trace_id=trace_id,
    )
    return row


def build_warning_raised_event(
    warning: models.Warning, sample: dict, trace_id: str, occurred_at
) -> dict:
    """构造契约 ``WarningRaisedEvent`` 报文。

    结构与 ``contracts/examples/warning-raised.json`` 一致，
    可被 ``warning-raised.payload.schema.json`` 与事件包络 schema 校验通过。
    """
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": "WarningRaised",
        "schemaVersion": SCHEMA_VERSION,
        "occurredAt": to_rfc3339(occurred_at),
        "sourceMember": SOURCE_MEMBER,
        "traceId": trace_id,
        "payload": {
            "warningId": warning.warning_id,
            "equipmentId": warning.equipment_id,
            "riskLevel": warning.risk_level,
            "healthScore": round(float(warning.health_score), 1),
            "suspectedFault": warning.suspected_fault,
            "recommendedAction": warning.recommended_action,
            "warningAt": to_rfc3339(warning.warning_at),
            "modelVersion": warning.model_version,
            "metricSnapshot": {
                "sampleId": sample["sampleId"],
                "measuredAt": to_rfc3339(parse_rfc3339(sample["measuredAt"])),
                "temperatureC": sample["temperatureC"],
                "vibrationMmS": sample["vibrationMmS"],
                "currentA": sample["currentA"],
                "rotationalSpeedRpm": sample["rotationalSpeedRpm"],
            },
        },
    }
