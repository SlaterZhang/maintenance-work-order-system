"""预警状态机与结论映射单元测试。

覆盖契约 ``warningStatus`` 五个取值的全部合法/非法迁移，
以及 ``docs/06`` 第 10 节第 5 条的维修结论映射。
"""

import pytest

from src.domain.enums import (
    MaintenanceResult as R,
    RiskLevel,
    WarningAction as A,
    WarningStatus as W,
    escalate_risk,
)
from src.domain.errors import InvalidStateTransitionError
from src.domain.state_machine import (
    TERMINAL_STATUSES,
    acknowledge_action,
    action_for_conclusion,
    transition_warning,
)


# ---------- 合法迁移 ----------
@pytest.mark.parametrize(
    "current,action,expected",
    [
        (W.OPEN, A.ACKNOWLEDGE, W.ACKNOWLEDGED),
        (W.OPEN, A.LINK_TO_ORDER, W.LINKED_TO_ORDER),
        (W.ACKNOWLEDGED, A.LINK_TO_ORDER, W.LINKED_TO_ORDER),
        (W.OPEN, A.RESOLVE, W.RESOLVED),
        (W.ACKNOWLEDGED, A.RESOLVE, W.RESOLVED),
        (W.LINKED_TO_ORDER, A.RESOLVE, W.RESOLVED),
        (W.OPEN, A.MARK_FALSE_POSITIVE, W.FALSE_POSITIVE),
        (W.ACKNOWLEDGED, A.MARK_FALSE_POSITIVE, W.FALSE_POSITIVE),
        (W.LINKED_TO_ORDER, A.MARK_FALSE_POSITIVE, W.FALSE_POSITIVE),
        (W.OPEN, A.HOLD_ACKNOWLEDGED, W.ACKNOWLEDGED),
        (W.LINKED_TO_ORDER, A.HOLD_ACKNOWLEDGED, W.ACKNOWLEDGED),
        # 已关联工单后仍可确认，状态保持 LINKED_TO_ORDER
        (W.LINKED_TO_ORDER, A.ACKNOWLEDGE_LINKED, W.LINKED_TO_ORDER),
    ],
)
def test_valid_transitions(current, action, expected):
    assert transition_warning(current, action) is expected


# ---------- 非法迁移 ----------
@pytest.mark.parametrize(
    "current,action",
    [
        (W.ACKNOWLEDGED, A.ACKNOWLEDGE),      # 不能重复确认
        (W.LINKED_TO_ORDER, A.ACKNOWLEDGE),   # 已建单不能再确认
        (W.RESOLVED, A.ACKNOWLEDGE),          # 已闭环
        (W.FALSE_POSITIVE, A.ACKNOWLEDGE),
        (W.RESOLVED, A.LINK_TO_ORDER),
        (W.FALSE_POSITIVE, A.LINK_TO_ORDER),
        (W.RESOLVED, A.RESOLVE),
        (W.FALSE_POSITIVE, A.MARK_FALSE_POSITIVE),
    ],
)
def test_invalid_transitions(current, action):
    with pytest.raises(InvalidStateTransitionError):
        transition_warning(current, action)


def test_terminal_statuses_accept_no_action():
    """RESOLVED 与 FALSE_POSITIVE 是终态，任何动作都必须被拒绝。"""
    assert TERMINAL_STATUSES == {W.RESOLVED, W.FALSE_POSITIVE}
    for status in TERMINAL_STATUSES:
        for action in A:
            with pytest.raises(InvalidStateTransitionError):
                transition_warning(status, action)


def test_unknown_action_is_rejected():
    with pytest.raises(InvalidStateTransitionError):
        transition_warning(W.OPEN, "NOT_AN_ACTION")  # type: ignore[arg-type]


def test_invalid_transition_message_contains_states():
    with pytest.raises(InvalidStateTransitionError) as excinfo:
        transition_warning(W.RESOLVED, A.ACKNOWLEDGE)
    assert "RESOLVED" in str(excinfo.value)
    assert "ACKNOWLEDGE" in str(excinfo.value)


# ---------- 结论 -> 动作 ----------
@pytest.mark.parametrize(
    "result,effective,expected",
    [
        (R.RECOVERED, True, A.RESOLVE),
        (R.RECOVERED, False, A.MARK_FALSE_POSITIVE),
        (R.PARTIALLY_RECOVERED, True, A.HOLD_ACKNOWLEDGED),
        (R.PARTIALLY_RECOVERED, False, A.HOLD_ACKNOWLEDGED),
        (R.NOT_RECOVERED, True, None),
        (R.NOT_RECOVERED, False, None),
    ],
)
def test_conclusion_mapping(result, effective, expected):
    """docs/06 第 10 节第 5 条 + FALSE_POSITIVE 的模块内判定。"""
    assert action_for_conclusion(result, effective) is expected


# ---------- 风险升级 ----------
@pytest.mark.parametrize(
    "current,expected",
    [
        (RiskLevel.LOW, RiskLevel.MEDIUM),
        (RiskLevel.MEDIUM, RiskLevel.HIGH),
        (RiskLevel.HIGH, RiskLevel.CRITICAL),
        (RiskLevel.CRITICAL, RiskLevel.CRITICAL),  # 封顶
    ],
)
def test_escalate_risk(current, expected):
    assert escalate_risk(current) is expected


# ---------- 确认动作选择 ----------
def test_acknowledge_action_from_open():
    assert acknowledge_action(W.OPEN) is A.ACKNOWLEDGE


def test_acknowledge_action_from_linked_keeps_status():
    assert acknowledge_action(W.LINKED_TO_ORDER) is A.ACKNOWLEDGE_LINKED


def test_acknowledge_action_rejects_double_acknowledgement():
    """一条预警只能确认一次：已确认的预警即便状态未变也必须拒绝。"""
    for status in (W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER):
        with pytest.raises(InvalidStateTransitionError):
            acknowledge_action(status, already_acknowledged=True)


def test_acknowledge_action_from_terminal_raises():
    for status in TERMINAL_STATUSES:
        with pytest.raises(InvalidStateTransitionError):
            transition_warning(status, acknowledge_action(status))


def test_acknowledge_linked_is_rejected_from_other_states():
    for status in (W.OPEN, W.ACKNOWLEDGED, W.RESOLVED, W.FALSE_POSITIVE):
        with pytest.raises(InvalidStateTransitionError):
            transition_warning(status, A.ACKNOWLEDGE_LINKED)
