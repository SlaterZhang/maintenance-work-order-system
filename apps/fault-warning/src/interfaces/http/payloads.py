"""契约请求体逐字段校验。

为什么不用 FastAPI 的 Pydantic 请求模型
---------------------------------------
契约（``docs/06`` 第 1 节）要求失败响应统一为 ``ErrorResponse``，
并包含 ``code`` / ``traceId`` / ``details[].field``。
FastAPI 对请求体校验失败会返回它自己的 422 结构，不符合契约。
因此 B 的写接口统一以 ``body: dict`` 接收，在这里集中校验，
把**所有**字段问题一次性收集进 ``VALIDATION_ERROR`` 的 ``details``，
而不是遇到第一个错误就返回。
"""

import re

from src.domain.enums import MaintenanceResult
from src.domain.errors import ValidationError
from src.domain.ids import (
    EQUIPMENT_ID_PATTERN,
    ORDER_ID_PATTERN,
    USER_ID_PATTERN,
    UUID_PATTERN,
    WARNING_ID_PATTERN,
    parse_rfc3339,
)

HEALTH_EVALUATION_FIELDS = {"evaluationId", "equipmentId", "requestedAt", "sample"}
SAMPLE_FIELDS = {
    "sampleId",
    "measuredAt",
    "temperatureC",
    "vibrationMmS",
    "currentA",
    "rotationalSpeedRpm",
}
ACKNOWLEDGEMENT_FIELDS = {"operatorId", "expectedVersion", "comment"}
CONCLUSION_ENVELOPE_FIELDS = {
    "eventId",
    "eventType",
    "schemaVersion",
    "occurredAt",
    "sourceMember",
    "traceId",
    "payload",
}
CONCLUSION_PAYLOAD_FIELDS = {
    "orderId",
    "warningId",
    "equipmentId",
    "rootCause",
    "measures",
    "result",
    "completedAt",
    "effective",
    "submittedBy",
    "downtimeMinutes",
}

SCHEMA_VERSION_PATTERN = r"^2\.[0-9]+$"

_MISSING = object()


class PayloadValidator:
    """累积式字段校验器；全部检查完毕后由 :meth:`finish` 统一抛出。"""

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix
        self.errors: list[dict] = []

    # ---------- 基础设施 ----------
    def fail(self, field: str, reason: str) -> None:
        self.errors.append({"field": f"{self.prefix}{field}", "reason": reason})

    def child(self, prefix: str) -> "PayloadValidator":
        """派生一个带前缀的子校验器，与父校验器共享错误列表。"""
        nested = PayloadValidator(f"{self.prefix}{prefix}")
        nested.errors = self.errors
        return nested

    def finish(self) -> None:
        if self.errors:
            raise ValidationError("请求字段校验失败", details=self.errors)

    def reject_unknown(self, obj: dict, allowed: set[str]) -> None:
        """契约所有请求体都是 ``additionalProperties: false``。"""
        if not isinstance(obj, dict):
            return
        for key in obj:
            if key not in allowed:
                self.fail(key, "契约未定义的字段")

    def _get(self, obj, key: str, required: bool):
        if not isinstance(obj, dict) or key not in obj:
            if required:
                self.fail(key, "必填字段缺失")
            return _MISSING
        return obj[key]

    # ---------- 类型 ----------
    def string(
        self,
        obj,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        pattern: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> str | None:
        value = self._get(obj, key, required)
        if value is _MISSING:
            return None
        if value is None:
            if nullable:
                return None
            self.fail(key, "不允许为 null")
            return None
        if not isinstance(value, str):
            self.fail(key, "必须是字符串")
            return None
        if pattern and not re.fullmatch(pattern, value):
            self.fail(key, f"格式必须匹配 {pattern}")
        if min_length is not None and len(value) < min_length:
            self.fail(key, f"长度不得小于 {min_length}")
        if max_length is not None and len(value) > max_length:
            self.fail(key, f"长度不得超过 {max_length}")
        return value

    def uuid_string(self, obj, key: str, *, required: bool = True) -> str | None:
        return self.string(obj, key, required=required, pattern=UUID_PATTERN)

    def datetime_string(
        self, obj, key: str, *, required: bool = True, nullable: bool = False
    ) -> str | None:
        value = self.string(obj, key, required=required, nullable=nullable)
        if value is None:
            return None
        try:
            parse_rfc3339(value)
        except ValueError:
            self.fail(key, "必须是 RFC 3339 时间，例如 2026-09-17T08:30:00Z")
        return value

    def number(
        self,
        obj,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float | None:
        value = self._get(obj, key, required)
        if value is _MISSING:
            return None
        if value is None:
            if nullable:
                return None
            self.fail(key, "不允许为 null")
            return None
        # bool 是 int 的子类，必须显式排除
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.fail(key, "必须是数字")
            return None
        number = float(value)
        if minimum is not None and number < minimum:
            self.fail(key, f"不得小于 {minimum}")
        if maximum is not None and number > maximum:
            self.fail(key, f"不得大于 {maximum}")
        return number

    def integer(
        self,
        obj,
        key: str,
        *,
        required: bool = True,
        nullable: bool = False,
        minimum: int | None = None,
    ) -> int | None:
        value = self._get(obj, key, required)
        if value is _MISSING:
            return None
        if value is None:
            if nullable:
                return None
            self.fail(key, "不允许为 null")
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(key, "必须是整数")
            return None
        if minimum is not None and value < minimum:
            self.fail(key, f"不得小于 {minimum}")
        return value

    def boolean(
        self, obj, key: str, *, required: bool = True, nullable: bool = False
    ) -> bool | None:
        value = self._get(obj, key, required)
        if value is _MISSING:
            return None
        if value is None:
            if nullable:
                return None
            self.fail(key, "不允许为 null")
            return None
        if not isinstance(value, bool):
            self.fail(key, "必须是布尔值")
            return None
        return value

    def const(self, obj, key: str, expected: str, *, required: bool = True) -> str | None:
        value = self.string(obj, key, required=required)
        if value is not None and value != expected:
            self.fail(key, f"必须为 {expected}")
        return value

    def enum_value(self, obj, key: str, enum_cls, *, required: bool = True):
        value = self._get(obj, key, required)
        if value is _MISSING:
            return None
        if not isinstance(value, str):
            self.fail(key, "必须是字符串枚举值")
            return None
        try:
            return enum_cls(value)
        except ValueError:
            allowed = " / ".join(member.value for member in enum_cls)
            self.fail(key, f"必须是 {allowed} 之一")
            return None


def parse_sample(parent: PayloadValidator, raw) -> dict | None:
    """校验 ``TelemetrySample``（契约 additionalProperties=false）。"""
    if raw is None:
        parent.fail("sample", "必填字段缺失")
        return None
    if not isinstance(raw, dict):
        parent.fail("sample", "必须是对象")
        return None

    child = parent.child("sample.")
    child.reject_unknown(raw, SAMPLE_FIELDS)
    sample = {
        "sampleId": child.uuid_string(raw, "sampleId"),
        "measuredAt": child.datetime_string(raw, "measuredAt"),
        "temperatureC": child.number(
            raw, "temperatureC", minimum=-50, maximum=250
        ),
        "vibrationMmS": child.number(raw, "vibrationMmS", minimum=0, maximum=200),
        "currentA": child.number(raw, "currentA", minimum=0, maximum=10000),
        "rotationalSpeedRpm": child.number(
            raw, "rotationalSpeedRpm", minimum=0, maximum=100000
        ),
    }
    return sample


def parse_health_evaluation(body) -> dict:
    """校验 ``HealthEvaluationRequest``（C-INT-02）。"""
    if not isinstance(body, dict):
        raise ValidationError(
            "请求体必须是 JSON 对象",
            details=[{"field": "<root>", "reason": "期望 JSON 对象"}],
        )

    validator = PayloadValidator()
    validator.reject_unknown(body, HEALTH_EVALUATION_FIELDS)

    result = {
        "evaluationId": validator.uuid_string(body, "evaluationId"),
        "equipmentId": validator.string(
            body, "equipmentId", pattern=EQUIPMENT_ID_PATTERN
        ),
        "requestedAt": validator.datetime_string(body, "requestedAt"),
        "sample": parse_sample(validator, body.get("sample")),
    }
    validator.finish()
    return result


def parse_acknowledgement(body) -> dict:
    """校验 ``WarningAcknowledgementRequest``（B-API-03）。"""
    if not isinstance(body, dict):
        raise ValidationError(
            "请求体必须是 JSON 对象",
            details=[{"field": "<root>", "reason": "期望 JSON 对象"}],
        )

    validator = PayloadValidator()
    validator.reject_unknown(body, ACKNOWLEDGEMENT_FIELDS)

    result = {
        "operatorId": validator.string(body, "operatorId", pattern=USER_ID_PATTERN),
        "expectedVersion": validator.integer(body, "expectedVersion", minimum=0),
        "comment": validator.string(
            body, "comment", required=False, nullable=True, max_length=300
        ),
    }
    validator.finish()
    return result


def parse_maintenance_conclusion_event(body) -> dict:
    """校验 ``MaintenanceConclusionEvent``（C-INT-05，含事件包络）。"""
    if not isinstance(body, dict):
        raise ValidationError(
            "请求体必须是 JSON 对象",
            details=[{"field": "<root>", "reason": "期望 JSON 对象"}],
        )

    envelope = PayloadValidator()
    envelope.reject_unknown(body, CONCLUSION_ENVELOPE_FIELDS)

    event = {
        "eventId": envelope.uuid_string(body, "eventId"),
        "eventType": envelope.const(body, "eventType", "MaintenanceConclusionReported"),
        "schemaVersion": envelope.string(
            body, "schemaVersion", pattern=SCHEMA_VERSION_PATTERN
        ),
        "occurredAt": envelope.datetime_string(body, "occurredAt"),
        "sourceMember": envelope.const(body, "sourceMember", "MEMBER_C"),
        "traceId": envelope.string(body, "traceId", min_length=8, max_length=64),
    }

    raw_payload = body.get("payload")
    if raw_payload is None:
        envelope.fail("payload", "必填字段缺失")
        payload = None
    elif not isinstance(raw_payload, dict):
        envelope.fail("payload", "必须是对象")
        payload = None
    else:
        child = envelope.child("payload.")
        child.reject_unknown(raw_payload, CONCLUSION_PAYLOAD_FIELDS)
        payload = {
            "orderId": child.string(
                raw_payload, "orderId", pattern=ORDER_ID_PATTERN
            ),
            # warningId 必填但允许为 null（人工报修工单没有预警）
            "warningId": child.string(
                raw_payload, "warningId", nullable=True, pattern=WARNING_ID_PATTERN
            ),
            "equipmentId": child.string(
                raw_payload, "equipmentId", pattern=EQUIPMENT_ID_PATTERN
            ),
            "rootCause": child.string(
                raw_payload, "rootCause", min_length=1, max_length=500
            ),
            "measures": child.string(
                raw_payload, "measures", min_length=1, max_length=1000
            ),
            "result": child.enum_value(
                raw_payload, "result", MaintenanceResult
            ),
            "completedAt": child.datetime_string(raw_payload, "completedAt"),
            "effective": child.boolean(raw_payload, "effective"),
            "submittedBy": child.string(
                raw_payload, "submittedBy", pattern=USER_ID_PATTERN
            ),
            "downtimeMinutes": child.integer(
                raw_payload, "downtimeMinutes", required=False, nullable=True, minimum=0
            ),
        }

    envelope.finish()
    event["payload"] = payload
    return event
