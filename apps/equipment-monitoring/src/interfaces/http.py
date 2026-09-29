import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, AsyncIterator
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.application.service import EquipmentService
from src.config import Settings
from src.domain.errors import DomainError
from src.domain.models import (
    CreateEquipmentRequest,
    Equipment,
    EquipmentPage,
    EquipmentStatus,
    EquipmentStatusChangedEvent,
    ErrorResponse,
    EventAcceptedResponse,
    FieldViolation,
    TelemetryBatchRequest,
    TelemetryIngestionResponse,
    TelemetryPage,
    UpdateEquipmentRequest,
    utc_now,
)
from src.infrastructure.sqlite_repository import SQLiteEquipmentRepository
from src.infrastructure.health_client import (
    HealthEvaluationClient,
    HttpHealthEvaluationClient,
)


LOGGER = logging.getLogger(__name__)
EQUIPMENT_ID_PATTERN = r"^EQ-[0-9]{6}$"


def _request_trace_id(request: Request) -> str:
    cached = getattr(request.state, "trace_id", None)
    if cached:
        return cached
    candidate = request.headers.get("X-Trace-Id", "")
    if 8 <= len(candidate) <= 64:
        request.state.trace_id = candidate
    else:
        request.state.trace_id = f"trace-{uuid4().hex[:24]}"
    return request.state.trace_id


def _error_content(
    request: Request,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> dict:
    return ErrorResponse(
        code=code,
        message=message,
        traceId=_request_trace_id(request),
        timestamp=utc_now(),
        details=[FieldViolation.model_validate(item) for item in (details or [])],
    ).model_dump(mode="json")


def create_app(
    settings: Settings | None = None,
    health_evaluation_client: HealthEvaluationClient | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    repository = SQLiteEquipmentRepository(active_settings.database_path)
    outbound_client = health_evaluation_client
    if outbound_client is None and active_settings.warning_service_url:
        outbound_client = HttpHealthEvaluationClient(
            active_settings.warning_service_url,
            active_settings.internal_api_token,
            active_settings.outbound_timeout_seconds,
        )
    service = EquipmentService(repository, outbound_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        repository.initialize()
        if active_settings.seed_on_start:
            repository.seed_if_empty()
        service.dispatch_pending_health_evaluations()
        yield

    app = FastAPI(
        title="设备资产与运行监测服务",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.service = service
    app.state.settings = active_settings

    def get_service() -> EquipmentService:
        return service

    def require_internal_token(
        request: Request,
        x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> None:
        expected = active_settings.internal_api_token
        if expected and x_internal_token != expected:
            raise DomainError(401, "AUTH_TOKEN_INVALID", "内部服务凭证无效")

    def require_telemetry_writer(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> None:
        expected = active_settings.internal_api_token
        if not expected:
            return
        bearer_present = bool(authorization and authorization.startswith("Bearer "))
        if x_internal_token != expected and not bearer_present:
            raise DomainError(401, "AUTH_TOKEN_INVALID", "遥测写入凭证无效")

    @app.middleware("http")
    async def trace_header(request: Request, call_next):
        current_trace_id = _request_trace_id(request)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = current_trace_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_content(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"] if part != "body")
            details.append({"field": location or "body", "reason": error["msg"]})
        return JSONResponse(
            status_code=400,
            content=_error_content(
                request, "VALIDATION_ERROR", "请求参数校验失败", details
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled equipment service error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_content(request, "INTERNAL_ERROR", "服务内部错误"),
        )

    TraceHeader = Annotated[
        str | None, Header(alias="X-Trace-Id", min_length=8, max_length=64)
    ]
    RequiredTraceHeader = Annotated[
        str, Header(alias="X-Trace-Id", min_length=8, max_length=64)
    ]
    IdempotencyHeader = Annotated[UUID, Header(alias="Idempotency-Key")]
    EquipmentPath = Annotated[str, Path(pattern=EQUIPMENT_ID_PATTERN)]

    @app.get(
        "/api/v1/equipment",
        response_model=EquipmentPage,
        operation_id="listEquipment",
        tags=["A-设备监测"],
    )
    def list_equipment(
        trace_id: TraceHeader = None,
        keyword: Annotated[str | None, Query(max_length=50)] = None,
        production_line_id: Annotated[
            str | None, Query(alias="productionLineId", max_length=32)
        ] = None,
        equipment_status: Annotated[EquipmentStatus | None, Query(alias="status")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
        current_service: EquipmentService = Depends(get_service),
    ) -> EquipmentPage:
        return current_service.list_equipment(
            keyword, production_line_id, equipment_status, page, page_size
        )

    @app.post(
        "/api/v1/equipment",
        response_model=Equipment,
        status_code=status.HTTP_201_CREATED,
        operation_id="createEquipment",
        tags=["A-设备监测"],
    )
    def create_equipment(
        body: CreateEquipmentRequest,
        idempotency_key: IdempotencyHeader,
        trace_id: TraceHeader = None,
        current_service: EquipmentService = Depends(get_service),
    ) -> Equipment:
        return current_service.create_equipment(body, str(idempotency_key))

    @app.get(
        "/api/v1/equipment/{equipmentId}",
        response_model=Equipment,
        operation_id="getEquipmentById",
        tags=["A-设备监测"],
    )
    def get_equipment(
        equipmentId: EquipmentPath,
        trace_id: TraceHeader = None,
        current_service: EquipmentService = Depends(get_service),
    ) -> Equipment:
        return current_service.get_equipment(equipmentId)

    @app.patch(
        "/api/v1/equipment/{equipmentId}",
        response_model=Equipment,
        operation_id="updateEquipment",
        tags=["A-设备监测"],
    )
    def update_equipment(
        equipmentId: EquipmentPath,
        body: UpdateEquipmentRequest,
        idempotency_key: IdempotencyHeader,
        trace_id: TraceHeader = None,
        current_service: EquipmentService = Depends(get_service),
    ) -> Equipment:
        return current_service.update_equipment(
            equipmentId, body, str(idempotency_key)
        )

    @app.get(
        "/api/v1/equipment/{equipmentId}/telemetry",
        response_model=TelemetryPage,
        operation_id="listEquipmentTelemetry",
        tags=["A-设备监测"],
    )
    def list_telemetry(
        equipmentId: EquipmentPath,
        trace_id: TraceHeader = None,
        from_time: Annotated[datetime | None, Query(alias="from")] = None,
        to_time: Annotated[datetime | None, Query(alias="to")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
        current_service: EquipmentService = Depends(get_service),
    ) -> TelemetryPage:
        return current_service.list_telemetry(
            equipmentId, from_time, to_time, page, page_size
        )

    @app.post(
        "/api/v1/equipment/{equipmentId}/telemetry",
        response_model=TelemetryIngestionResponse,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="ingestEquipmentTelemetry",
        tags=["A-设备监测"],
        dependencies=[Depends(require_telemetry_writer)],
    )
    def ingest_telemetry(
        request: Request,
        equipmentId: EquipmentPath,
        body: TelemetryBatchRequest,
        idempotency_key: IdempotencyHeader,
        trace_id: TraceHeader = None,
        current_service: EquipmentService = Depends(get_service),
    ) -> TelemetryIngestionResponse:
        return current_service.ingest_telemetry(
            equipmentId,
            body,
            str(idempotency_key),
            _request_trace_id(request),
        )

    @app.post(
        "/api/v1/integration/equipment-status-events",
        response_model=EventAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        operation_id="consumeEquipmentStatusChanged",
        tags=["A-设备监测"],
        dependencies=[Depends(require_internal_token)],
    )
    def consume_equipment_status_event(
        body: EquipmentStatusChangedEvent,
        trace_id: RequiredTraceHeader,
        idempotency_key: IdempotencyHeader,
        current_service: EquipmentService = Depends(get_service),
    ) -> EventAcceptedResponse:
        return current_service.consume_status_event(
            body, str(idempotency_key), trace_id
        )

    return app
