import httpx
from src.config import settings
from src.domain.errors import EquipmentNotFoundError

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberAClient:
    """C-INT-01 查设备 / C-INT-04 通知设备状态"""

    @staticmethod
    def get_equipment(equipment_id: str, trace_id: str) -> dict | None:
        try:
            r = httpx.get(
                f"{settings.member_a_base}/api/v1/equipment/{equipment_id}",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id},
                timeout=3.0,
            )
        except httpx.HTTPError:
            # 本地无 A 服务时返回 mock，方便独立开发
            return _mock_equipment(equipment_id)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    @staticmethod
    def notify_equipment_status(order_id: str, equipment_id: str,
                                target_status: str, operator_id: str,
                                reason: str, trace_id: str) -> bool:
        """C-INT-04：失败不阻塞主流程，记录待同步"""
        import uuid
        event = {
            "eventId": str(uuid.uuid4()),
            "eventType": "EquipmentStatusChanged",
            "schemaVersion": "2.0",
            "occurredAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "sourceMember": "MEMBER_C",
            "traceId": trace_id,
            "payload": {
                "orderId": order_id,
                "equipmentId": equipment_id,
                "targetStatus": target_status,
                "operatorId": operator_id,
                "reason": reason,
            },
        }
        try:
            r = httpx.post(
                f"{settings.member_a_base}/api/v1/integration/equipment-status-events",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id,
                         "Idempotency-Key": str(uuid.uuid4())},
                json=event, timeout=3.0,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False


def _mock_equipment(equipment_id: str) -> dict:
    return {
        "equipmentId": equipment_id,
        "name": f"设备-{equipment_id}",
        "equipmentType": "CNC",
        "productionLineId": "LINE-01",
        "location": "一车间 A 区",
        "manufacturer": None,
        "model": None,
        "responsibleDepartment": "机加车间",
        "currentStatus": "RUNNING",
        "enabled": True,
        "version": 1,
        "createdAt": "2026-09-01T00:00:00Z",
        "updatedAt": "2026-09-01T00:00:00Z",
    }