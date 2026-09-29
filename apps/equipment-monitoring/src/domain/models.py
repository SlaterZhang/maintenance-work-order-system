from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


EQUIPMENT_ID_PATTERN = r"^EQ-[0-9]{6}$"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("时间必须是带 UTC 时区的 RFC 3339 时间")
    return value.astimezone(timezone.utc)


def to_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class EquipmentStatus(str, Enum):
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    STOPPED = "STOPPED"
    MAINTAINING = "MAINTAINING"
    TRIAL_RUNNING = "TRIAL_RUNNING"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_contract_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return to_rfc3339(value)
        return value


class Equipment(ContractModel):
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    equipmentType: str = Field(min_length=1, max_length=50)
    productionLineId: str = Field(min_length=1, max_length=32)
    location: str = Field(min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    responsibleDepartment: str | None = Field(default=None, max_length=100)
    currentStatus: EquipmentStatus
    enabled: bool
    version: int = Field(ge=0)
    createdAt: datetime
    updatedAt: datetime

    _created_utc = field_validator("createdAt")(require_utc)
    _updated_utc = field_validator("updatedAt")(require_utc)


class CreateEquipmentRequest(ContractModel):
    name: str = Field(min_length=1, max_length=100)
    equipmentType: str = Field(min_length=1, max_length=50)
    productionLineId: str = Field(min_length=1, max_length=32)
    location: str = Field(min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    responsibleDepartment: str | None = Field(default=None, max_length=100)


class UpdateEquipmentRequest(ContractModel):
    expectedVersion: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    productionLineId: str | None = Field(default=None, min_length=1, max_length=32)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    responsibleDepartment: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> "UpdateEquipmentRequest":
        if not (self.model_fields_set - {"expectedVersion"}):
            raise ValueError("至少提供一个需要修改的字段")
        return self

    def changes(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.model_fields_set
            if field_name != "expectedVersion"
        }


class EquipmentPage(ContractModel):
    items: list[Equipment]
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1)
    total: int = Field(ge=0)
    totalPages: int = Field(ge=0)


class TelemetrySample(ContractModel):
    sampleId: UUID
    measuredAt: datetime
    temperatureC: float = Field(ge=-50, le=250)
    vibrationMmS: float = Field(ge=0, le=200)
    currentA: float = Field(ge=0, le=10000)
    rotationalSpeedRpm: float = Field(ge=0, le=100000)

    _measured_utc = field_validator("measuredAt")(require_utc)


class TelemetryBatchRequest(ContractModel):
    batchId: UUID
    source: Literal["SIMULATOR", "DEVICE_GATEWAY", "MANUAL_TEST"]
    samples: list[TelemetrySample] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_samples(self) -> "TelemetryBatchRequest":
        sample_ids = [sample.sampleId for sample in self.samples]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("同一批次中 sampleId 不得重复")
        return self


class TelemetryIngestionResponse(ContractModel):
    batchId: UUID
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    acceptedCount: int = Field(ge=0)
    rejectedCount: int = Field(ge=0)
    duplicate: bool
    receivedAt: datetime

    _received_utc = field_validator("receivedAt")(require_utc)


class TelemetryPage(ContractModel):
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    items: list[TelemetrySample]
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1)
    total: int = Field(ge=0)
    totalPages: int = Field(ge=0)


class HealthEvaluationRequest(ContractModel):
    evaluationId: UUID
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    requestedAt: datetime
    sample: TelemetrySample

    _requested_utc = field_validator("requestedAt")(require_utc)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HealthEvaluationResponse(ContractModel):
    evaluationId: UUID
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    healthScore: float = Field(ge=0, le=100)
    riskLevel: RiskLevel
    suspectedFault: str = Field(max_length=200)
    recommendedAction: str = Field(max_length=500)
    modelVersion: str = Field(max_length=32)
    evaluatedAt: datetime
    warningId: str | None = Field(
        default=None, pattern=r"^WARN-[0-9]{8}-[0-9]{4}$"
    )

    _evaluated_utc = field_validator("evaluatedAt")(require_utc)


class EquipmentStatusChangedPayload(ContractModel):
    orderId: str = Field(pattern=r"^WO-[0-9]{8}-[0-9]{4}$")
    equipmentId: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    targetStatus: EquipmentStatus
    operatorId: str = Field(pattern=r"^USER-[A-Z0-9-]{1,27}$")
    reason: str = Field(min_length=1, max_length=300)


class EquipmentStatusChangedEvent(ContractModel):
    eventId: UUID
    eventType: Literal["EquipmentStatusChanged"]
    schemaVersion: str = Field(pattern=r"^2\.[0-9]+$")
    occurredAt: datetime
    sourceMember: Literal["MEMBER_C"]
    traceId: str = Field(min_length=8, max_length=64)
    payload: EquipmentStatusChangedPayload

    _occurred_utc = field_validator("occurredAt")(require_utc)


class EventAcceptedResponse(ContractModel):
    accepted: Literal[True] = True
    duplicate: bool
    traceId: str


class FieldViolation(ContractModel):
    field: str
    reason: str


class ErrorResponse(ContractModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str
    traceId: str = Field(min_length=8, max_length=64)
    timestamp: datetime
    details: list[FieldViolation]

    _timestamp_utc = field_validator("timestamp")(require_utc)
