from datetime import datetime

from sqlalchemy.orm import Session

from src.config import iso_utc
from src.domain.errors import BadRequestError, EquipmentNotFoundError
from src.domain.models import Equipment, TelemetryBatch, TelemetrySampleRecord

TELEMETRY_SOURCES = ("SIMULATOR", "DEVICE_GATEWAY", "MANUAL_TEST")
SAMPLE_FIELDS = {
    "temperatureC": (-50.0, 250.0),
    "vibrationMmS": (0.0, 200.0),
    "currentA": (0.0, 10000.0),
    "rotationalSpeedRpm": (0.0, 100000.0),
}
MAX_SAMPLES_PER_BATCH = 500


def _get_equipment(db: Session, equipment_id: str) -> Equipment:
    equipment = (
        db.query(Equipment).filter(Equipment.equipment_id == equipment_id).first()
    )
    if equipment is None:
        raise EquipmentNotFoundError()
    return equipment


def _validate_batch_request(equipment_id: str, body: dict) -> None:
    batch_id = body.get("batchId")
    try:
        import uuid

        uuid.UUID(str(batch_id))
    except (ValueError, AttributeError):
        raise BadRequestError("batchId 必须为 UUID")

    if body.get("source") not in TELEMETRY_SOURCES:
        raise BadRequestError(f"source 必须为 {list(TELEMETRY_SOURCES)} 之一")

    samples = body.get("samples")
    if not isinstance(samples, list) or not (
            1 <= len(samples) <= MAX_SAMPLES_PER_BATCH):
        raise BadRequestError(f"samples 必须为 1~{MAX_SAMPLES_PER_BATCH} 条数组")

    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise BadRequestError(f"samples[{index}] 必须为对象")
        try:
            uuid.UUID(str(sample.get("sampleId")))
        except (ValueError, AttributeError):
            raise BadRequestError(f"samples[{index}].sampleId 必须为 UUID")
        if not sample.get("measuredAt"):
            raise BadRequestError(f"samples[{index}].measuredAt 必填")
        for field, (low, high) in SAMPLE_FIELDS.items():
            value = sample.get(field)
            if not isinstance(value, (int, float)):
                raise BadRequestError(f"samples[{index}].{field} 必须为数值")
            if not (low <= value <= high):
                raise BadRequestError(
                    f"samples[{index}].{field} 取值应在 [{low}, {high}] 内"
                )


def ingest_telemetry(db: Session, equipment_id: str, body: dict) -> dict:
    _get_equipment(db, equipment_id)
    _validate_batch_request(equipment_id, body)

    batch_id = str(body["batchId"])
    existing = (
        db.query(TelemetryBatch)
        .filter(TelemetryBatch.batch_id == batch_id)
        .first()
    )
    if existing is not None:
        return {
            "batchId": batch_id,
            "equipmentId": equipment_id,
            "acceptedCount": existing.accepted_count,
            "rejectedCount": 0,
            "duplicate": True,
            "receivedAt": iso_utc(existing.received_at),
        }

    accepted = 0
    rejected = 0
    for sample in body["samples"]:
        existed = (
            db.query(TelemetrySampleRecord)
            .filter(TelemetrySampleRecord.sample_id == str(sample["sampleId"]))
            .first()
        )
        if existed is not None:
            rejected += 1
            continue
        measured_raw = str(sample["measuredAt"])
        measured_at = datetime.fromisoformat(
            measured_raw.replace("Z", "+00:00"))
        db.add(TelemetrySampleRecord(
            sample_id=str(sample["sampleId"]),
            equipment_id=equipment_id,
            measured_at=measured_at,
            temperature_c=sample["temperatureC"],
            vibration_mm_s=sample["vibrationMmS"],
            current_a=sample["currentA"],
            rotational_speed_rpm=sample["rotationalSpeedRpm"],
        ))
        accepted += 1

    received_at = datetime.utcnow()
    db.add(TelemetryBatch(
        batch_id=batch_id,
        equipment_id=equipment_id,
        source=body["source"],
        accepted_count=accepted,
        received_at=received_at,
    ))
    db.commit()
    return {
        "batchId": batch_id,
        "equipmentId": equipment_id,
        "acceptedCount": accepted,
        "rejectedCount": rejected,
        "duplicate": False,
        "receivedAt": received_at.isoformat().replace("+00:00", "") + "Z",
    }


def list_telemetry(db: Session, equipment_id: str, from_time: str | None,
                   to_time: str | None, page: int, page_size: int) -> dict:
    _get_equipment(db, equipment_id)

    query = db.query(TelemetrySampleRecord).filter(
        TelemetrySampleRecord.equipment_id == equipment_id
    )
    if from_time:
        query = query.filter(
            TelemetrySampleRecord.measured_at >= datetime.fromisoformat(
                from_time.replace("Z", "+00:00"))
        )
    if to_time:
        query = query.filter(
            TelemetrySampleRecord.measured_at <= datetime.fromisoformat(
                to_time.replace("Z", "+00:00"))
        )
    total = query.count()
    records = (
        query.order_by(TelemetrySampleRecord.measured_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "equipmentId": equipment_id,
        "items": [{
            "sampleId": record.sample_id,
            "measuredAt": iso_utc(record.measured_at),
            "temperatureC": record.temperature_c,
            "vibrationMmS": record.vibration_mm_s,
            "currentA": record.current_a,
            "rotationalSpeedRpm": record.rotational_speed_rpm,
        } for record in records],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
    }
