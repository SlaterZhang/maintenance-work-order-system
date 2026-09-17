import uuid
import httpx
from datetime import datetime
from src.config import settings

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberBClient:
    """C-INT-05：发送 MaintenanceConclusionReported"""

    @staticmethod
    def send_conclusion(order_id: str, warning_id: str, equipment_id: str,
                        root_cause: str, measures: str, result: str,
                        completed_at, effective: bool, submitted_by: str,
                        trace_id: str) -> bool:
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
                         "Idempotency-Key": str(uuid.uuid4())},
                json=event, timeout=3.0,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False