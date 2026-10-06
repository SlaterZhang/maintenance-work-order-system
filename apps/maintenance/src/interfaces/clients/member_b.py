import uuid
import httpx
from datetime import datetime, timezone
from src.config import settings

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberBClient:
    """C-INT-05：发送 MaintenanceConclusionReported"""

    @staticmethod
    def send_conclusion(order_id: str, warning_id: str, equipment_id: str,
                        root_cause: str, measures: str, result: str,
                        completed_at, effective: bool, submitted_by: str,
                        trace_id: str) -> bool:
        if hasattr(completed_at, "isoformat") and completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        event = {
            "eventId": str(uuid.uuid4()),
            "eventType": "MaintenanceConclusionReported",
            "schemaVersion": "2.0",
            "occurredAt": datetime.utcnow().isoformat() + "Z",
            "sourceMember": "MEMBER_C",
            "traceId": trace_id,
            "payload": {
                "orderId": order_id,
                "warningId": warning_id,
                "equipmentId": equipment_id,
                "rootCause": root_cause,
                "measures": measures,
                "result": result,
                "completedAt": (completed_at.isoformat()
                                if hasattr(completed_at, "isoformat")
                                else completed_at),
                "effective": effective,
                "submittedBy": submitted_by,
                "downtimeMinutes": None,
            },
        }
        try:
            r = httpx.post(
                f"{settings.member_b_base}/api/v1/integration/maintenance-conclusions",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id,
                         "Idempotency-Key": event["eventId"]},
                json=event, timeout=3.0,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False

    @staticmethod
    def send_order_cancelled(order_id: str, warning_id: str, equipment_id: str,
                             cancelled_at, cancelled_by: str, reason: str,
                             trace_id: str) -> bool:
        """C-INT-08：发送 OrderCancelledReported（工单取消回流 B）。

        2026-10-07 新增：关联预警闭环为 CANCELLED，解除"已转工单"悬死态，
        设备再次异常时 B 才会新建预警并触发自动建单。
        """
        if hasattr(cancelled_at, "isoformat") and cancelled_at.tzinfo is None:
            cancelled_at = cancelled_at.replace(tzinfo=timezone.utc)
        event = {
            "eventId": str(uuid.uuid4()),
            "eventType": "OrderCancelledReported",
            "schemaVersion": "2.0",
            "occurredAt": datetime.utcnow().isoformat() + "Z",
            "sourceMember": "MEMBER_C",
            "traceId": trace_id,
            "payload": {
                "orderId": order_id,
                "warningId": warning_id,
                "equipmentId": equipment_id,
                "cancelledAt": (
                    cancelled_at.isoformat()
                    if hasattr(cancelled_at, "isoformat") else cancelled_at
                ),
                "cancelledBy": cancelled_by,
                "reason": reason or "",
            },
        }
        try:
            r = httpx.post(
                f"{settings.member_b_base}/api/v1/integration/order-cancellations",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id,
                         "Idempotency-Key": event["eventId"]},
                json=event, timeout=3.0,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False