"""业务标识的格式定义与生成。

格式依据 ``docs/06_详细接口约定与联调手册.md`` 第 4 节：

============= ============================== ======================
字段          格式                            示例
============= ============================== ======================
equipmentId   ``EQ-`` + 6 位数字               EQ-000001
warningId     ``WARN-YYYYMMDD-`` + 4 位数字    WARN-20260917-0001
orderId       ``WO-YYYYMMDD-`` + 4 位数字      WO-20260917-0001
userId        ``USER-`` + ``[A-Z0-9-]{1,27}``  USER-C-002
============= ============================== ======================

设计说明
--------
``WarningId`` 的后缀是**当日递增序号**，不是随机数：
随机数在批量评估时会发生碰撞，而 ``warning_id`` 上有唯一约束，
碰撞会直接把一次评估变成 500。序号的分配由
:func:`src.application.evaluation_service.allocate_warning_id` 在
数据库事务内完成，并带唯一约束重试，见该方法注释。
"""

import re
from datetime import datetime, timezone

EQUIPMENT_ID_PATTERN = r"^EQ-[0-9]{6}$"
WARNING_ID_PATTERN = r"^WARN-[0-9]{8}-[0-9]{4}$"
ORDER_ID_PATTERN = r"^WO-[0-9]{8}-[0-9]{4}$"
SPARE_PART_ID_PATTERN = r"^SP-[0-9]{6}$"
SPARE_REQUEST_ID_PATTERN = r"^SPR-[0-9]{8}-[0-9]{4}$"
USER_ID_PATTERN = r"^USER-[A-Z0-9-]{1,27}$"
UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

WARNING_ID_SEQUENCE_MAX = 9999

_WARNING_ID_RE = re.compile(r"^WARN-([0-9]{8})-([0-9]{4})$")


def utc_now() -> datetime:
    """返回带时区的当前 UTC 时间（不使用已废弃的 ``datetime.utcnow()``）。"""
    return datetime.now(timezone.utc)


def utc_day(moment: datetime | None = None) -> str:
    """返回 ``YYYYMMDD``（UTC）。"""
    return (moment or utc_now()).astimezone(timezone.utc).strftime("%Y%m%d")


def format_warning_id(day: str, sequence: int) -> str:
    """按 ``WARN-YYYYMMDD-NNNN`` 组装并校验取值范围。"""
    if not re.fullmatch(r"[0-9]{8}", day):
        raise ValueError(f"非法的日期片段：{day!r}")
    if not 1 <= sequence <= WARNING_ID_SEQUENCE_MAX:
        raise ValueError(
            f"预警序号超出范围（1..{WARNING_ID_SEQUENCE_MAX}）：{sequence}"
        )
    return f"WARN-{day}-{sequence:04d}"


def new_warning_id(sequence: int, moment: datetime | None = None) -> str:
    """用当日日期与给定序号生成 WarningId。"""
    return format_warning_id(utc_day(moment), sequence)


def parse_warning_id(warning_id: str) -> tuple[str, int]:
    """把 ``WARN-YYYYMMDD-NNNN`` 拆成 ``(day, sequence)``；格式错误抛 ValueError。"""
    match = _WARNING_ID_RE.fullmatch(warning_id or "")
    if not match:
        raise ValueError(f"非法 WarningId：{warning_id!r}")
    return match.group(1), int(match.group(2))


def to_rfc3339(moment: datetime) -> str:
    """把时间归一化成契约要求的 RFC 3339 UTC 字符串（``...Z``）。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_rfc3339(value: str) -> datetime:
    """解析 RFC 3339 时间戳，统一返回带 UTC 时区的 datetime。"""
    text = (value or "").strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
