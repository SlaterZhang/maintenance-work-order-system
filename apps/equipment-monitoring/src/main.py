import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid

from src.config import settings
from src.domain.errors import ContractError
from src.infrastructure.db import SessionLocal, init_db, seed_equipment
from src.interfaces.http import equipment, events, telemetry

app = FastAPI(
    title="成员A：设备资产与运行监测",
    version="2.0.0",
    description="对齐 contracts/openapi.yaml v2.0.0 的实现",
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
    with SessionLocal() as db:
        seed_equipment(db)


@app.exception_handler(ContractError)
async def contract_error_handler(request: Request, exc: ContractError):
    trace = request.headers.get("X-Trace-Id") or f"trace-{uuid.uuid4().hex[:16]}"
    return JSONResponse(status_code=exc.http_status, content=exc.to_response(trace))


app.include_router(equipment.router)
app.include_router(telemetry.router)
app.include_router(events.router)


@app.get("/health")
def health():
    return {"status": "UP", "service": "member-a", "port": settings.member_a_port}
