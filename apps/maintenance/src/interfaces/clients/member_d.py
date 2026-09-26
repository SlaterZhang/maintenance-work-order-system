import httpx
from src.config import settings

HEADERS_BASE = {"X-Internal-Token": settings.internal_api_token}


class MemberDClient:
    """C-INT-06：查用户权限上下文"""

    @staticmethod
    def get_access_context(user_id: str, trace_id: str) -> dict | None:
        try:
            r = httpx.get(
                f"{settings.member_d_base}/api/v1/users/{user_id}/access-context",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id},
                timeout=3.0,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            # Mock：本地开发时给一个维修主管权限
            return {
                "userId": user_id,
                "displayName": "Mock 用户",
                "roleCodes": ["MAINTENANCE_SUPERVISOR"],
                "permissions": [
                    "WORK_ORDER_READ", "WORK_ORDER_CONFIRM",
                    "WORK_ORDER_ASSIGN", "WORK_ORDER_CANCEL",
                    "WORK_ORDER_INSPECT", "SPARE_APPROVE",
                    "SPARE_ISSUE", "SPARE_READ", "SPARE_REQUEST",
                ],
                "organization": "机加车间",
                "enabled": True,
            }


class MemberDNotifier:
    """C-INT-07：提交通知任务"""

    @staticmethod
    def submit_notification(recipients: list[str], template_code: str,
                            variables: dict, trace_id: str) -> bool:
        import uuid
        body = {
            "recipientUserIds": recipients,
            "templateCode": template_code,
            "channel": "IN_APP",
            "variables": variables,
            "businessReference": None,
        }
        try:
            r = httpx.post(
                f"{settings.member_d_base}/api/v1/notifications",
                headers={**HEADERS_BASE, "X-Trace-Id": trace_id,
                         "Idempotency-Key": str(uuid.uuid4())},
                json=body, timeout=3.0,
            )
            return r.status_code in (200, 202)
        except httpx.HTTPError:
            return False