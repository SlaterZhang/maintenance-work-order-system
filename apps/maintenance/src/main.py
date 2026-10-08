from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid

from src.config import settings
from src.infrastructure.db import init_db
from src.interfaces.http import work_orders, spare_parts, integration
from src.domain.errors import ContractError


app = FastAPI(
    title="成员C：维修工单与备件管理",
    version="2.0.0",
    description="对齐 openapi.yaml v2.0.0 的实现",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.exception_handler(ContractError)
async def contract_error_handler(request: Request, exc: ContractError):
    trace = request.headers.get("X-Trace-Id") or f"trace-{uuid.uuid4().hex[:16]}"
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response(trace),
    )


app.include_router(integration.router)
app.include_router(work_orders.router)
app.include_router(spare_parts.router)


@app.get("/health")
def health():
    return {"status": "UP", "service": "member-c", "port": settings.member_c_port}