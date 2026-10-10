"""C 审计日志查询接口。

* C-API-09：``GET /api/v1/audit-logs``（登录身份即可），分页查询全链路操作留痕。

数据早已由 ``work_order_service._audit`` 写入 ``audit_log`` 表，
此前只是缺少查询入口——本模块只做**只读暴露**，不改变任何写入语义。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.application import work_order_service
from src.infrastructure.db import get_db
from src.interfaces.http.deps import operator_context, trace_id as get_trace_id

router = APIRouter(prefix="/api/v1", tags=["C-审计日志"])


def _optional_datetime(value: str | None) -> datetime | None:
    """解析 ISO-8601 字符串；非法值交由 FastAPI 层过滤，这里宽松处理。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    orderId: str | None = Query(default=None, max_length=60),
    operatorId: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    from_: str | None = Query(default=None, alias="from", max_length=40),
    to: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_trace_id: str = Depends(get_trace_id),
    db: Session = Depends(get_db),
):
    """C-API-09：分页查询审计日志，支持工单号/操作人/动作/时间范围过滤。"""
    operator_context(request, x_trace_id)
    return work_order_service.list_audit_logs(
        db,
        order_id=orderId,
        operator_id=operatorId,
        action=action,
        from_at=_optional_datetime(from_),
        to_at=_optional_datetime(to),
        page=page,
        page_size=pageSize,
    )
