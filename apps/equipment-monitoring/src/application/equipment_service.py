import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy.orm import Session

from src.config import iso_utc
from src.domain.errors import BadRequestError, EquipmentNotFoundError
from src.domain.models import Equipment, EquipmentStatusEvent

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts"

EQUIPMENT_STATUS_CHANGED_EVENT_TYPE = "EquipmentStatusChanged"
EQUIPMENT_STATUS_CHANGED_SOURCE = "MEMBER_C"


@lru_cache(maxsize=4)
def _load_json_schema(name: str) -> dict:
    return json.loads(
        (CONTRACTS_DIR / "schemas" / name).read_text(encoding="utf-8")
    )


def _validate_event(body: dict) -> None:
    envelope_schema = _load_json_schema("event-envelope.schema.json")
    payload_schema = _load_json_schema("equipment-status-changed.payload.schema.json")
    envelope_validator = Draft202012Validator(
        envelope_schema, format_checker=FormatChecker()
    )
    errors = sorted(envelope_validator.iter_errors(body), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise BadRequestError(f"事件包络不合法：{location}: {first.message}")

    payload_validator = Draft202012Validator(
        payload_schema, format_checker=FormatChecker()
    )
    errors = sorted(
        payload_validator.iter_errors(body.get("payload")), key=lambda e: list(e.path)
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise BadRequestError(f"事件载荷不合法：{location}: {first.message}")

    if body.get("eventType") != EQUIPMENT_STATUS_CHANGED_EVENT_TYPE:
        raise BadRequestError(f"eventType 必须为 {EQUIPMENT_STATUS_CHANGED_EVENT_TYPE}")
    if body.get("sourceMember") != EQUIPMENT_STATUS_CHANGED_SOURCE:
        raise BadRequestError(f"sourceMember 必须为 {EQUIPMENT_STATUS_CHANGED_SOURCE}")


def get_equipment(db: Session, equipment_id: str) -> dict:
    equipment = (
        db.query(Equipment).filter(Equipment.equipment_id == equipment_id).first()
    )
    if equipment is None:
        raise EquipmentNotFoundError()
    return {
        "equipmentId": equipment.equipment_id,
        "name": equipment.name,
        "equipmentType": equipment.equipment_type,
        "productionLineId": equipment.production_line_id,
        "location": equipment.location,
        "manufacturer": equipment.manufacturer,
        "model": equipment.model,
        "responsibleDepartment": equipment.responsible_department,
        "currentStatus": equipment.current_status,
        "enabled": equipment.enabled,
        "version": equipment.version,
        "createdAt": iso_utc(equipment.created_at),
        "updatedAt": iso_utc(equipment.updated_at),
    }


def ingest_status_event(db: Session, body: dict, trace_id: str) -> dict:
    _validate_event(body)
    event_id = body["eventId"]

    existing = (
        db.query(EquipmentStatusEvent)
        .filter(EquipmentStatusEvent.event_id == event_id)
        .first()
    )
    if existing is not None:
        return {"accepted": True, "duplicate": True, "traceId": trace_id}

    payload = body["payload"]
    equipment = (
        db.query(Equipment)
        .filter(Equipment.equipment_id == payload["equipmentId"])
        .first()
    )
    if equipment is None:
        raise EquipmentNotFoundError()

    occurred_at = datetime.fromisoformat(body["occurredAt"].replace("Z", "+00:00"))
    db.add(
        EquipmentStatusEvent(
            event_id=event_id,
            order_id=payload["orderId"],
            equipment_id=payload["equipmentId"],
            target_status=payload["targetStatus"],
            operator_id=payload["operatorId"],
            reason=payload["reason"],
            occurred_at=occurred_at,
            trace_id=trace_id,
        )
    )
    equipment.current_status = payload["targetStatus"]
    equipment.version += 1
    db.commit()

    return {"accepted": True, "duplicate": False, "traceId": trace_id}
