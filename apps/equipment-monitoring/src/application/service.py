from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime
from typing import Any

from src.domain.errors import DomainError
from src.domain.models import (
    CreateEquipmentRequest,
    Equipment,
    EquipmentPage,
    EquipmentStatus,
    EquipmentStatusChangedEvent,
    EventAcceptedResponse,
    HealthEvaluationRequest,
    TelemetryBatchRequest,
    TelemetryIngestionResponse,
    TelemetryPage,
    UpdateEquipmentRequest,
    require_utc,
    to_rfc3339,
)
from src.infrastructure.health_client import HealthEvaluationClient
from src.infrastructure.sqlite_repository import SQLiteEquipmentRepository


LOGGER = logging.getLogger(__name__)


def request_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EquipmentService:
    def __init__(
        self,
        repository: SQLiteEquipmentRepository,
        health_evaluation_client: HealthEvaluationClient | None = None,
    ) -> None:
        self.repository = repository
        self.health_evaluation_client = health_evaluation_client

    def get_equipment(self, equipment_id: str) -> Equipment:
        return Equipment.model_validate(self.repository.get_equipment(equipment_id))

    def list_equipment(
        self,
        keyword: str | None,
        production_line_id: str | None,
        status: EquipmentStatus | None,
        page: int,
        page_size: int,
    ) -> EquipmentPage:
        items, total = self.repository.list_equipment(
            keyword.strip() if keyword else None,
            production_line_id,
            status.value if isinstance(status, EquipmentStatus) else status,
            page,
            page_size,
        )
        return EquipmentPage(
            items=items,
            page=page,
            pageSize=page_size,
            total=total,
            totalPages=math.ceil(total / page_size),
        )

    def create_equipment(
        self, request: CreateEquipmentRequest, idempotency_key: str
    ) -> Equipment:
        body = request.model_dump(mode="json")
        result = self.repository.create_equipment(body, idempotency_key, request_hash(body))
        return Equipment.model_validate(result)

    def update_equipment(
        self,
        equipment_id: str,
        request: UpdateEquipmentRequest,
        idempotency_key: str,
    ) -> Equipment:
        body = request.model_dump(mode="json", exclude_unset=True)
        result = self.repository.update_equipment(
            equipment_id,
            request.expectedVersion,
            request.changes(),
            idempotency_key,
            request_hash(body),
        )
        return Equipment.model_validate(result)

    def ingest_telemetry(
        self,
        equipment_id: str,
        request: TelemetryBatchRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> TelemetryIngestionResponse:
        body = request.model_dump(mode="json")
        result = self.repository.ingest_telemetry(
            equipment_id, body, idempotency_key, request_hash(body), trace_id
        )
        self.dispatch_pending_health_evaluations()
        return TelemetryIngestionResponse.model_validate(result)

    def dispatch_pending_health_evaluations(self) -> int:
        if self.health_evaluation_client is None:
            return 0
        sent_count = 0
        for pending in self.repository.list_pending_health_evaluations():
            try:
                request = HealthEvaluationRequest.model_validate(pending["request"])
                self.health_evaluation_client.evaluate(
                    request,
                    pending["traceId"],
                    pending["evaluationId"],
                )
            except Exception as exc:  # outbound failure remains retryable in the outbox
                self.repository.mark_health_evaluation_failed(
                    pending["evaluationId"], str(exc)
                )
                LOGGER.warning(
                    "Health evaluation delivery deferred for evaluationId=%s",
                    pending["evaluationId"],
                )
                break
            self.repository.mark_health_evaluation_sent(pending["evaluationId"])
            sent_count += 1
        return sent_count

    def list_telemetry(
        self,
        equipment_id: str,
        from_time: datetime | None,
        to_time: datetime | None,
        page: int,
        page_size: int,
    ) -> TelemetryPage:
        normalized_from = require_utc(from_time) if from_time else None
        normalized_to = require_utc(to_time) if to_time else None
        if normalized_from and normalized_to and normalized_from > normalized_to:
            raise DomainError(
                400,
                "VALIDATION_ERROR",
                "起始时间不能晚于结束时间",
                [{"field": "from", "reason": "必须早于或等于 to"}],
            )
        items, total = self.repository.list_telemetry(
            equipment_id,
            to_rfc3339(normalized_from) if normalized_from else None,
            to_rfc3339(normalized_to) if normalized_to else None,
            page,
            page_size,
        )
        return TelemetryPage(
            equipmentId=equipment_id,
            items=items,
            page=page,
            pageSize=page_size,
            total=total,
            totalPages=math.ceil(total / page_size),
        )

    def consume_status_event(
        self,
        event: EquipmentStatusChangedEvent,
        idempotency_key: str,
        header_trace_id: str,
    ) -> EventAcceptedResponse:
        if event.traceId != header_trace_id:
            raise DomainError(
                400,
                "VALIDATION_ERROR",
                "请求头与事件中的链路标识不一致",
                [{"field": "traceId", "reason": "必须与 X-Trace-Id 一致"}],
            )
        body = event.model_dump(mode="json")
        result = self.repository.consume_status_event(
            body, idempotency_key, request_hash(body)
        )
        return EventAcceptedResponse.model_validate(result)
