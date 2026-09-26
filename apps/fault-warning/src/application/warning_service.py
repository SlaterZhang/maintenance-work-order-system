import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy.orm import Session

from src.config import settings
from src.domain import risk_engine
from src.domain.errors import BadRequestError, WarningNotFoundError
from src.domain.models import HealthEvaluation, MaintenanceConclusionEvent, Warning

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts"

EQUIPMENT_ID_PATTERN = r"^EQ-[0-9]{6}$"
WARNING_RAISED_EVENT_TYPE = "WarningRaised"
CONCLUSION_EVENT_TYPE = "MaintenanceConclusionReported"

SAMPLE_FIELDS = {
    "sampleId": uuid.UUID,
    "measuredAt": str,
    "temperatureC": (-50.0, 250.0),
    "vibrationMmS": (0.0, 200.0),
    "currentA": (0.0, 10000.0),
    "rotationalSpeedRpm": (0.0, 100000.0),
}


def _load_json_schema(name: str) -> dict:
    return json.loads(
        (CONTRACTS_DIR / "schemas" / name).read_text(encoding="utf-8")
    )


def _validate_conclusion_event(body: dict) -> None:
    envelope_validator = Draft202012Validator(
        _load_json_schema("event-envelope.schema.json"), format_checker=FormatChecker()
    )
    errors = sorted(envelope_validator.iter_errors(body), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise BadRequestError(f"事件包络不合法：{location}: {first.message}")

    payload_validator = Draft202012Validator(
        _load_json_schema("maintenance-conclusion.payload.schema.json"),
        format_checker=FormatChecker(),
    )
    errors = sorted(
        payload_validator.iter_errors(body.get("payload")), key=lambda e: list(e.path)
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise BadRequestError(f"事件载荷不合法：{location}: {first.message}")

    if body.get("eventType") != CONCLUSION_EVENT_TYPE:
        raise BadRequestError(f"eventType 必须为 {CONCLUSION_EVENT_TYPE}")
    if body.get("sourceMember") != "MEMBER_C":
        raise BadRequestError("sourceMember 必须为 MEMBER_C")


def validate_evaluation_request(request: dict) -> None:
    try:
        uuid.UUID(str(request.get("evaluationId", "")))
    except ValueError:
        raise BadRequestError("evaluationId 必须为 UUID")

    equipment_id = str(request.get("equipmentId", ""))
    import re

    if not re.fullmatch(EQUIPMENT_ID_PATTERN, equipment_id):
        raise BadRequestError("equipmentId 必须形如 EQ-000001")

    if not request.get("requestedAt"):
        raise BadRequestError("requestedAt 必填")

    sample = request.get("sample")
    if not isinstance(sample, dict):
        raise BadRequestError("sample 必填")
    for field, spec in SAMPLE_FIELDS.items():
        if field not in sample:
            raise BadRequestError(f"sample.{field} 必填")
        if isinstance(spec, tuple):
            value = sample[field]
            if not isinstance(value, (int, float)):
                raise BadRequestError(f"sample.{field} 必须为数值")
            low, high = spec
            if not (low <= value <= high):
                raise BadRequestError(
                    f"sample.{field} 取值应在 [{low}, {high}] 内"
                )


def _thresholds() -> dict:
    return {
        "low": settings.low_score_threshold,
        "medium": settings.medium_score_threshold,
        "high": settings.high_score_threshold,
    }


def create_warning_id(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"WARN-{today}-"
    count = db.query(Warning).filter(Warning.warning_id.startswith(prefix)).count()
    return f"{prefix}{count + 1:04d}"


def evaluate_and_raise(db: Session, request: dict) -> dict:
    evaluation_id = str(request["evaluationId"])
    existing = (
        db.query(HealthEvaluation)
        .filter(HealthEvaluation.evaluation_id == evaluation_id)
        .first()
    )
    if existing is not None:
        return json.loads(existing.response_body)

    result = risk_engine.evaluate(request["sample"], _thresholds())
    equipment_id = request["equipmentId"]
    now = datetime.now(timezone.utc)
    warning_id = None

    if result["riskLevel"] in {"HIGH", "CRITICAL"}:
        warning = (
            db.query(Warning)
            .filter(
                Warning.equipment_id == equipment_id,
                Warning.status.in_(("OPEN", "ACKNOWLEDGED")),
            )
            .first()
        )
        if warning is None:
            warning = Warning(
                warning_id=create_warning_id(db),
                equipment_id=equipment_id,
                risk_level=result["riskLevel"],
                health_score=result["healthScore"],
                suspected_fault=result["suspectedFault"],
                recommended_action=result["recommendedAction"],
                status="OPEN",
                warning_at=now,
                model_version=settings.model_version,
            )
            db.add(warning)
        else:
            warning.risk_level = result["riskLevel"]
            warning.health_score = result["healthScore"]
            warning.suspected_fault = result["suspectedFault"]
            warning.recommended_action = result["recommendedAction"]
        db.flush()
        warning_id = warning.warning_id

    response = {
        "evaluationId": evaluation_id,
        "equipmentId": equipment_id,
        **result,
        "modelVersion": settings.model_version,
        "evaluatedAt": now.isoformat().replace("+00:00", "Z"),
        "warningId": warning_id,
    }
    db.add(
        HealthEvaluation(
            evaluation_id=evaluation_id,
            equipment_id=equipment_id,
            response_body=json.dumps(response, ensure_ascii=False),
        )
    )
    db.commit()
    return response


def build_warning_raised_event(db: Session, warning_id: str, sample: dict, trace_id: str) -> dict:
    warning = db.query(Warning).filter(Warning.warning_id == warning_id).first()
    if warning is None:
        raise WarningNotFoundError()
    occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    warning_at = warning.warning_at
    if warning_at.tzinfo is None:
        warning_at = warning_at.replace(tzinfo=timezone.utc)
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": WARNING_RAISED_EVENT_TYPE,
        "schemaVersion": "2.0",
        "occurredAt": occurred_at,
        "sourceMember": "MEMBER_B",
        "traceId": trace_id,
        "payload": {
            "warningId": warning.warning_id,
            "equipmentId": warning.equipment_id,
            "riskLevel": warning.risk_level,
            "healthScore": warning.health_score,
            "suspectedFault": warning.suspected_fault,
            "recommendedAction": warning.recommended_action,
            "warningAt": warning_at.isoformat().replace("+00:00", "Z"),
            "modelVersion": warning.model_version,
            "metricSnapshot": {
                "sampleId": sample["sampleId"],
                "measuredAt": sample["measuredAt"],
                "temperatureC": sample["temperatureC"],
                "vibrationMmS": sample["vibrationMmS"],
                "currentA": sample["currentA"],
                "rotationalSpeedRpm": sample["rotationalSpeedRpm"],
            },
        },
    }


def mark_warning_sent(db: Session, warning_id: str) -> None:
    warning = db.query(Warning).filter(Warning.warning_id == warning_id).first()
    if warning is not None:
        warning.event_sent = True
        db.commit()


def receive_conclusion(db: Session, body: dict, trace_id: str) -> dict:
    _validate_conclusion_event(body)
    event_id = body["eventId"]

    existing = (
        db.query(MaintenanceConclusionEvent)
        .filter(MaintenanceConclusionEvent.event_id == event_id)
        .first()
    )
    if existing is not None:
        return {"accepted": True, "duplicate": True, "traceId": trace_id}

    payload = body["payload"]
    warning_id = payload.get("warningId")

    if warning_id is not None:
        warning = (
            db.query(Warning).filter(Warning.warning_id == warning_id).first()
        )
        if warning is None:
            raise WarningNotFoundError()
        if payload.get("effective") is True:
            warning.status = "RESOLVED"
            warning.version += 1

    db.add(
        MaintenanceConclusionEvent(
            event_id=event_id,
            warning_id=warning_id,
            order_id=payload["orderId"],
            result=payload["result"],
            effective=payload["effective"],
            payload=json.dumps(payload, ensure_ascii=False),
            trace_id=trace_id,
        )
    )
    db.commit()
    return {"accepted": True, "duplicate": False, "traceId": trace_id}


# ---------- B-API-01/02/03：预警查询与确认 ----------
def _serialize_warning(warning) -> dict:
    def _iso(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")

    return {
        "warningId": warning.warning_id,
        "equipmentId": warning.equipment_id,
        "riskLevel": warning.risk_level,
        "healthScore": warning.health_score,
        "suspectedFault": warning.suspected_fault,
        "recommendedAction": warning.recommended_action,
        "status": warning.status,
        "warningAt": _iso(warning.warning_at),
        "modelVersion": warning.model_version,
        "linkedOrderId": warning.linked_order_id,
        "acknowledgedBy": warning.acknowledged_by,
        "acknowledgedAt": _iso(warning.acknowledged_at),
        "version": warning.version,
    }


def list_warnings(db: Session, equipment_id: str | None, risk_level: str | None,
                  status: str | None, page: int, page_size: int) -> dict:
    from src.domain.models import Warning as WarningModel

    query = db.query(WarningModel)
    if equipment_id:
        query = query.filter(WarningModel.equipment_id == equipment_id)
    if risk_level:
        query = query.filter(WarningModel.risk_level == risk_level)
    if status:
        query = query.filter(WarningModel.status == status)
    total = query.count()
    items = (
        query.order_by(WarningModel.warning_at.desc(), WarningModel.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_serialize_warning(item) for item in items],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
    }


def get_warning(db: Session, warning_id: str) -> dict:
    from src.domain.models import Warning as WarningModel

    warning = (
        db.query(WarningModel)
        .filter(WarningModel.warning_id == warning_id)
        .first()
    )
    if warning is None:
        raise WarningNotFoundError()
    return _serialize_warning(warning)


def acknowledge_warning(db: Session, warning_id: str, body: dict) -> dict:
    from datetime import datetime, timezone

    from src.domain.errors import BadRequestError, ConflictError
    from src.domain.models import Warning as WarningModel

    warning = (
        db.query(WarningModel)
        .filter(WarningModel.warning_id == warning_id)
        .first()
    )
    if warning is None:
        raise WarningNotFoundError()

    operator_id = body.get("operatorId")
    if not operator_id or not isinstance(operator_id, str):
        raise BadRequestError("operatorId 必填")
    expected_version = body.get("expectedVersion")
    if not isinstance(expected_version, int):
        raise BadRequestError("expectedVersion 必填且为整数")
    comment = body.get("comment")
    if comment is not None and len(str(comment)) > 300:
        raise BadRequestError("comment 长度不得超过 300")

    if expected_version != warning.version:
        raise ConflictError(
            f"版本冲突：期望 {expected_version} 实际 {warning.version}"
        )
    if warning.status != "OPEN":
        raise ConflictError(f"当前状态 {warning.status} 不允许确认")

    warning.status = "ACKNOWLEDGED"
    warning.acknowledged_by = operator_id
    warning.acknowledged_at = datetime.now(timezone.utc)
    warning.version += 1
    db.commit()
    return _serialize_warning(warning)
