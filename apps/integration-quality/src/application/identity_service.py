import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.domain.enums import (
    TEMPLATE_CODES,
    notification_channel_values,
    permission_code_values,
    role_code_values,
)
from src.domain.errors import BadRequestError, UserNotFoundError
from src.domain.models import NotificationTask, User

USER_ID_MAX_LENGTH = 32


def get_access_context(db: Session, user_id: str) -> dict:
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None or not user.enabled:
        raise UserNotFoundError()
    role_codes = json.loads(user.role_codes)
    permissions = json.loads(user.permissions)
    valid_roles = set(role_code_values())
    valid_permissions = set(permission_code_values())
    unknown_roles = [code for code in role_codes if code not in valid_roles]
    unknown_permissions = [code for code in permissions if code not in valid_permissions]
    if unknown_roles or unknown_permissions:
        raise BadRequestError(
            "种子数据与公共枚举不一致",
            details={
                "roles": unknown_roles,
                "permissions": unknown_permissions,
            },
        )
    return {
        "userId": user.user_id,
        "displayName": user.display_name,
        "roleCodes": role_codes,
        "permissions": permissions,
        "organization": user.organization,
        "enabled": user.enabled,
    }


def _validate_notification_request(request: dict) -> None:
    recipients = request.get("recipientUserIds")
    if not isinstance(recipients, list) or not recipients:
        raise BadRequestError("recipientUserIds 必须为非空数组")
    if len(recipients) != len(set(recipients)):
        raise BadRequestError("recipientUserIds 不得重复")
    for user_id in recipients:
        if not isinstance(user_id, str) or not 1 <= len(user_id) <= USER_ID_MAX_LENGTH:
            raise BadRequestError(f"recipientUserIds 含非法值：{user_id}")

    template_code = request.get("templateCode")
    if template_code not in TEMPLATE_CODES:
        raise BadRequestError(f"templateCode 必须为 {TEMPLATE_CODES} 之一")

    channel = request.get("channel")
    if channel not in notification_channel_values():
        raise BadRequestError(f"channel 必须为 {list(notification_channel_values())} 之一")

    variables = request.get("variables")
    if not isinstance(variables, dict) or not all(
        isinstance(value, str) for value in variables.values()
    ):
        raise BadRequestError("variables 必须为字符串字典")

    business_reference = request.get("businessReference")
    if business_reference is not None and len(business_reference) > 64:
        raise BadRequestError("businessReference 长度不得超过 64")


def submit_notification(db: Session, request: dict, idem_key: str, trace_id: str) -> dict:
    _validate_notification_request(request)

    existing = (
        db.query(NotificationTask)
        .filter(NotificationTask.idempotency_key == idem_key)
        .first()
    )
    if existing is not None:
        return {
            "notificationId": existing.notification_id,
            "accepted": True,
            "duplicate": True,
            "traceId": trace_id,
        }

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"NOTICE-{today}-"
    count = (
        db.query(NotificationTask)
        .filter(NotificationTask.notification_id.startswith(prefix))
        .count()
    )
    notification_id = f"{prefix}{count + 1:04d}"

    db.add(
        NotificationTask(
            idempotency_key=idem_key,
            notification_id=notification_id,
            payload=json.dumps(request, ensure_ascii=False),
            trace_id=trace_id,
        )
    )
    db.commit()
    return {
        "notificationId": notification_id,
        "accepted": True,
        "duplicate": False,
        "traceId": trace_id,
    }
