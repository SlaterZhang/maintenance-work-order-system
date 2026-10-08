import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid

from src.config import settings
from src.domain.errors import ContractError
from src.infrastructure.db import SessionLocal, init_db, seed_users
from src.interfaces.http import auth, identity, notifications

app = FastAPI(
    title="成员D：系统集成与质量保障",
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
        seed_users(db)


@app.exception_handler(ContractError)
async def contract_error_handler(request: Request, exc: ContractError):
    trace = request.headers.get("X-Trace-Id") or f"trace-{uuid.uuid4().hex[:16]}"
    return JSONResponse(status_code=exc.http_status, content=exc.to_response(trace))


app.include_router(auth.router)
app.include_router(identity.router)
app.include_router(notifications.router)


@app.get("/health")
def health():
    return {"status": "UP", "service": "member-d", "port": settings.member_d_port}
