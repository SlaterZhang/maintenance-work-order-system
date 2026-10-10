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


def list_user_summaries(
    db: Session,
    role_codes_filter: str | None,
    page: int,
    page_size: int,
) -> dict:
    """D-API-03：分页查询用户摘要（看板派单选人等场景）。

    只返回 userId/displayName/roleCodes/organization/enabled——不含口令
    哈希等敏感字段；鉴权口径为登录身份（Bearer），与工单看板一致。
    ``role_codes_filter`` 为逗号分隔的角色码（命中任一即返回）。
    """
    import json as _json

    wanted = None
    if role_codes_filter:
        wanted = {c.strip() for c in role_codes_filter.split(",") if c.strip()}

    users = db.query(User).order_by(User.user_id).all()
    if wanted:
        def _matches(user: User) -> bool:
            try:
                return bool(set(_json.loads(user.role_codes)) & wanted)
            except _json.JSONDecodeError:
                return False
        users = [u for u in users if _matches(u)]

    total = len(users)
    start = (page - 1) * page_size
    items = users[start:start + page_size]
    return {
        "items": [
            {
                "userId": u.user_id,
                "displayName": u.display_name,
                "roleCodes": _json.loads(u.role_codes),
                "organization": u.organization,
                "enabled": u.enabled,
            }
            for u in items
        ],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
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


def _serialize_notification(task: NotificationTask) -> dict:
    """通知任务 -> 契约 DTO。

    ``payload`` 是提交方原样落库的 JSON 字符串（列本身无结构化字段），
    这里**解析后再返回**，避免前端拿到需要二次解析的字符串；
    解析失败时退回 ``None`` 并保留原始文本，不让一条坏数据打断整页。
    """
    parsed = None
    try:
        parsed = json.loads(task.payload)
    except (ValueError, TypeError):
        parsed = None
    return {
        "notificationId": task.notification_id,
        "idempotencyKey": task.idempotency_key,
        "recipientUserIds": (parsed or {}).get("recipientUserIds") or [],
        "templateCode": (parsed or {}).get("templateCode"),
        "channel": (parsed or {}).get("channel"),
        "variables": (parsed or {}).get("variables") or {},
        "businessReference": (parsed or {}).get("businessReference"),
        "traceId": task.trace_id,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
    }


def list_notifications(
    db: Session,
    *,
    recipient_user_id: str | None = None,
    template_code: str | None = None,
    channel: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """D-API-04：分页查询通知任务，按 ``createdAt`` 降序。

    接收人/模板/渠道都在 ``payload`` JSON 里，SQLite 无 JSON 索引可用，
    故按接收人过滤时先在 Python 侧筛选 id 集合再取页——通知量级很小
    （业务流只在关键节点投递），这样比引入 JSON1 扩展依赖更简单可靠。
    """
    query = db.query(NotificationTask)
    if template_code:
        query = query.filter(NotificationTask.payload.like(
            f'%"templateCode": "{template_code}"%'))
    if channel:
        query = query.filter(NotificationTask.payload.like(
            f'%"channel": "{channel}"%'))

    items = query.order_by(NotificationTask.created_at.desc(),
                           NotificationTask.id.desc()).all()
    if recipient_user_id:
        items = [
            task for task in items
            if recipient_user_id in (_serialize_notification(task)["recipientUserIds"])
        ]

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    return {
        "items": [_serialize_notification(task) for task in page_items],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size if page_size else 0,
    }
