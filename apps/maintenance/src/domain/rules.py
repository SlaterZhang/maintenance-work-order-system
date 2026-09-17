from datetime import datetime, timedelta, timezone
from .enums import RiskLevel, WorkOrderPriority, RISK_TO_PRIORITY

# 风险等级 -> 响应小时（用于 dueAt）
RESPONSE_HOURS = {
    RiskLevel.CRITICAL: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.MEDIUM: 8,
    RiskLevel.LOW: 24,
}

# 允许自动建单的风险等级（契约 C-INT-03：HIGH/CRITICAL）
AUTO_ORDER_RISK_LEVELS = {RiskLevel.HIGH, RiskLevel.CRITICAL}


def calc_due_at(risk: RiskLevel, base: datetime | None = None) -> datetime:
    base = base or datetime.now(timezone.utc)
    return base + timedelta(hours=RESPONSE_HOURS[risk])


def map_priority(risk: RiskLevel) -> WorkOrderPriority:
    return RISK_TO_PRIORITY[risk]


def can_auto_create_order(risk: RiskLevel) -> bool:
    return risk in AUTO_ORDER_RISK_LEVELS