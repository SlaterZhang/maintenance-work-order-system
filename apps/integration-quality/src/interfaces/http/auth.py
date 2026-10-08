from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.application import auth_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import trace_id

router = APIRouter(prefix="/api/v1/auth", tags=["D-API-01 登录"])


@router.post("/login")
def login(
    body: dict,
    x_trace_id: str = Depends(trace_id),
    db: Session = Depends(get_db),
):
    """D-API-01：用户名密码登录换 JWT"""
    return auth_service.login(db, body)
