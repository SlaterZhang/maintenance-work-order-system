from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DomainError(Exception):
    status_code: int
    code: str
    message: str
    details: list[dict[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message


def not_found() -> DomainError:
    return DomainError(404, "EQUIPMENT_NOT_FOUND", "设备不存在")


def version_conflict(expected: int, actual: int) -> DomainError:
    return DomainError(
        409,
        "VERSION_CONFLICT",
        "设备版本已变更，请重新查询后再修改",
        [{"field": "expectedVersion", "reason": f"期望 {expected}，当前 {actual}"}],
    )


def idempotency_conflict() -> DomainError:
    return DomainError(
        409,
        "IDEMPOTENCY_CONFLICT",
        "相同幂等键不能用于不同请求",
    )
