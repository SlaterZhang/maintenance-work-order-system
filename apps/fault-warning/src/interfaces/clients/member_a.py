"""调用成员 A 的 C-INT-01：查询设备权威档案。

B 不维护设备主档（``docs/06`` 第 3 节），评估前必须向 A 确认设备存在。

与成员 C 实现的差异
-------------------
C 的 ``MemberAClient.get_equipment`` 在任何网络异常时**静默返回伪造的 mock 设备**，
会让系统对着不存在的设备建单。本模块把 mock 降级收敛为显式开关
``ALLOW_CLIENT_MOCK``：

* ``True``（仅本地单品开发）：降级返回 mock，并在返回值上标注来源；
* ``False``（联调、演示、CI）：不可达即失败，向上抛 500 ``INTERNAL_ERROR``，
  宁可不评估也不伪造事实。
"""

import httpx

from src.config import settings
from src.domain.errors import InternalError


def equipment_url(equipment_id: str) -> str:
    return f"{settings.equipment_service_url}/api/v1/equipment/{equipment_id}"


def fetch_recent_telemetry(
    equipment_id: str, trace_id: str, limit: int = 24
) -> list[dict] | None:
    """查询 A 的最近遥测样本（阶段3：退化趋势外推的数据源）。

    :returns: 样本列表（``measuredAt`` 最新的在前）；任何失败返回
        ``None``——趋势是增强信息，取不到就降级为 UNKNOWN，绝不阻塞评估。
    """
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Trace-Id": trace_id,
    }
    try:
        response = httpx.get(
            f"{settings.equipment_service_url}"
            f"/api/v1/equipment/{equipment_id}/telemetry",
            params={"pageSize": limit},
            headers=headers,
            timeout=settings.client_timeout_seconds,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    items = response.json().get("items")
    return items if isinstance(items, list) else None


def get_equipment(equipment_id: str, trace_id: str) -> dict | None:
    """查询设备档案。

    :returns: 设备字典；设备不存在（HTTP 404）返回 ``None``。
    :raises InternalError: 无法访问 A 且未开启 mock 降级。
    """
    headers = {
        "X-Internal-Token": settings.internal_api_token,
        "X-Trace-Id": trace_id,
    }
    try:
        response = httpx.get(
            equipment_url(equipment_id),
            headers=headers,
            timeout=settings.client_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        if settings.allow_client_mock:
            return _mock_equipment(equipment_id)
        raise InternalError(
            f"无法访问设备服务（C-INT-01），评估未完成：{type(exc).__name__}"
        ) from exc

    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        if settings.allow_client_mock:
            return _mock_equipment(equipment_id)
        raise InternalError(
            f"设备服务返回 HTTP {response.status_code}，评估未完成"
        )
    return response.json()


def _mock_equipment(equipment_id: str) -> dict:
    """本地开发用的最小设备档案。字段与契约 ``Equipment`` 保持同名。"""
    return {
        "equipmentId": equipment_id,
        "name": f"设备-{equipment_id}",
        "equipmentType": "CNC",
        "productionLineId": "LINE-01",
        "location": "一车间 A 区",
        "responsibleDepartment": "机加车间",
        "currentStatus": "RUNNING",
        "enabled": True,
        "version": 1,
        "source": "LOCAL_MOCK",
    }
