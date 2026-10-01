"""成员 B：故障预警与健康评估服务入口（本地端口 8102）。

对外提供（``contracts/openapi.yaml`` v2.0.0）
--------------------------------------------
=================================== =========== ================================
契约编号                             方法与路径    说明
=================================== =========== ================================
C-INT-02                             POST        /api/v1/health-evaluations
B-API-01                             GET         /api/v1/warnings
B-API-02                             GET         /api/v1/warnings/{warningId}
B-API-03                             POST        /api/v1/warnings/{warningId}/acknowledgements
C-INT-05                             POST        /api/v1/integration/maintenance-conclusions
=================================== =========== ================================

调用方（B 是调用方）
--------------------
* C-INT-01 ``GET {EQUIPMENT_SERVICE_URL}/api/v1/equipment/{equipmentId}`` 查设备；
* C-INT-03 ``POST {MAINTENANCE_SERVICE_URL}/api/v1/integration/warning-events`` 发预警；
* C-INT-06 ``GET {INTEGRATION_SERVICE_URL}/api/v1/users/{userId}/access-context`` 校验权限。

启动：``uvicorn src.main:app --port 8102``（在 ``apps/fault-warning`` 目录下执行）。
"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.config import settings
from src.domain.errors import ContractError, ValidationError
from src.infrastructure.db import init_db
from src.interfaces.http import health_evaluations, integration, warnings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fault-warning")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时建表。

    使用 lifespan 而不是已废弃的 ``@app.on_event("startup")``。
    """
    init_db()
    logger.info(
        "成员 B 已启动：端口 %s，模型 %s，mock 降级 %s",
        settings.member_b_port,
        settings.model_version,
        "开启（仅本地开发）" if settings.allow_client_mock else "关闭",
    )
    yield


app = FastAPI(
    title="成员 B：故障预警与健康评估",
    version="2.0.0",
    description=(
        "对齐 contracts/openapi.yaml v2.0.0 的 C-INT-02、B-API-01~03、C-INT-05"
    ),
    lifespan=lifespan,
)


def _resolve_trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or f"trace-{uuid.uuid4().hex[:16]}"


@app.exception_handler(ContractError)
async def contract_error_handler(request: Request, exc: ContractError) -> JSONResponse:
    """契约错误 -> ``ErrorResponse``（含 code / traceId / timestamp / details）。"""
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response(_resolve_trace_id(request)),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """把 FastAPI 默认的 422 改写成契约要求的 400 ``VALIDATION_ERROR``。"""
    details = []
    for error in exc.errors():
        location = [
            str(part) for part in error.get("loc", ()) if part not in ("body", "query")
        ]
        details.append(
            {
                "field": ".".join(location) or "<root>",
                "reason": str(error.get("msg", "字段不合法")),
            }
        )
    error = ValidationError("请求字段校验失败", details=details)
    return JSONResponse(
        status_code=error.http_status,
        content=error.to_response(_resolve_trace_id(request)),
    )


app.include_router(health_evaluations.router)
app.include_router(warnings.router)
app.include_router(integration.router)


@app.get("/health", tags=["运维"])
def health() -> dict:
    """存活探针。"""
    return {
        "status": "UP",
        "service": "member-b",
        "port": settings.member_b_port,
        "modelVersion": settings.model_version,
    }
