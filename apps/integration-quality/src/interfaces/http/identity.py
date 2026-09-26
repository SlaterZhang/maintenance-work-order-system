from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.application import identity_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import internal_token, trace_id

router = APIRouter(prefix="/api/v1/users", tags=["C-INT-06 身份权限上下文"])


@router.get("/{user_id}/access-context")
def get_user_access_context(
    user_id: str,
    x_trace_id: str = Depends(trace_id),
    _token: str = Depends(internal_token),
    db: Session = Depends(get_db),
):
    return identity_service.get_access_context(db, user_id)
