"""成员 B 的领域枚举。

公共枚举（``riskLevel`` / ``warningStatus`` / ``maintenanceResult`` /
``workOrderPriority``）必须与 ``contracts/shared-enums.json`` 完全一致，不得私增取值。

``WarningAction`` 是 B 模块内部状态机的动作集合，**不属于**公共契约：
``shared-enums.json`` 只冻结了 ``warningStatus``，没有定义预警动作，
因此这里作为模块私有实现，不对外暴露。
"""

from enum import Enum


class RiskLevel(str, Enum):
    """风险等级，见 contracts/shared-enums.json -> riskLevel。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class WarningStatus(str, Enum):
    """预警状态，见 contracts/shared-enums.json -> warningStatus。"""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    LINKED_TO_ORDER = "LINKED_TO_ORDER"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    # 2026-10-07 新增（契约 v2.1.0）：关联工单被取消后的闭环终态，
    # 终态预警不再被评估去重复用，设备再次异常将新建预警并自动建单
    CANCELLED = "CANCELLED"


class MaintenanceResult(str, Enum):
    """维修结论结果，见 contracts/shared-enums.json -> maintenanceResult。"""

    RECOVERED = "RECOVERED"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
    NOT_RECOVERED = "NOT_RECOVERED"


class WorkOrderPriority(str, Enum):
    """工单优先级，见 contracts/shared-enums.json -> workOrderPriority。"""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class WarningAction(str, Enum):
    """B 模块内部状态机动作（模块私有，不进入公共契约）。"""

    ACKNOWLEDGE = "ACKNOWLEDGE"
    ACKNOWLEDGE_LINKED = "ACKNOWLEDGE_LINKED"
    LINK_TO_ORDER = "LINK_TO_ORDER"
    RESOLVE = "RESOLVE"
    MARK_FALSE_POSITIVE = "MARK_FALSE_POSITIVE"
    HOLD_ACKNOWLEDGED = "HOLD_ACKNOWLEDGED"
    # 2026-10-07 新增：C-INT-08 工单取消回流（活跃态 → CANCELLED）
    ORDER_CANCELLED = "ORDER_CANCELLED"
    # 2026-10-07 新增（C-INT-09）：最新遥测证明设备已恢复正常（LOW），
    # 评估用例据此自动闭环仍处活跃态的预警（活跃态 → RESOLVED）
    AUTO_RESOLVE = "AUTO_RESOLVE"


class OutboxStatus(str, Enum):
    """待发送事件状态（模块内部）。"""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class OutboxEventType(str, Enum):
    """B 需要外送的事件/通知类型。"""

    WARNING_RAISED = "WarningRaised"
    WARNING_NOTIFICATION = "WarningNotification"
    # 2026-10-07 新增（C-INT-09）：预警被设备恢复正常自动闭环时，
    # 通知 C 结掉仍停在早期状态、从未进入维修的关联工单
    WARNING_RESOLVED = "WarningResolvedReported"


# 系统自动动作的操作人标识：必须满足契约 UserId 模式
# ``^USER-[A-Z0-9-]{1,27}$``，因此不能用裸 "system"。
SYSTEM_OPERATOR_ID = "USER-SYSTEM-AUTO"


# 契约 docs/06 第 6 节：风险等级 -> 工单优先级（唯一映射，B 与 C 共用同一张表）
RISK_TO_PRIORITY: dict[RiskLevel, WorkOrderPriority] = {
    RiskLevel.LOW: WorkOrderPriority.P4,
    RiskLevel.MEDIUM: WorkOrderPriority.P3,
    RiskLevel.HIGH: WorkOrderPriority.P2,
    RiskLevel.CRITICAL: WorkOrderPriority.P1,
}

# docs/06 第 6 节：只有 HIGH / CRITICAL 才向 C 发送 WarningRaised
ACTIONABLE_RISK_LEVELS: frozenset[RiskLevel] = frozenset(
    {RiskLevel.HIGH, RiskLevel.CRITICAL}
)

# 尚未闭环的预警状态：同一设备 + 同一疑似故障在这三个状态下复用原 WarningId
ACTIVE_WARNING_STATUSES: frozenset[WarningStatus] = frozenset(
    {
        WarningStatus.OPEN,
        WarningStatus.ACKNOWLEDGED,
        WarningStatus.LINKED_TO_ORDER,
    }
)

# 风险升级顺序（NOT_RECOVERED 时按此表升级一级）
_RISK_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
)


def escalate_risk(risk: RiskLevel) -> RiskLevel:
    """把风险等级向上提升一级；已是 CRITICAL 时保持不变。"""
    index = _RISK_ORDER.index(risk)
    return _RISK_ORDER[min(index + 1, len(_RISK_ORDER) - 1)]
