"""状态机单元测试：覆盖契约里所有 action 的合法/非法迁移"""
import pytest

from src.domain.enums import (
    WorkOrderAction as A, WorkOrderStatus as W,
    SpareRequestAction as SA, SpareRequestStatus as S,
)
from src.domain.errors import InvalidTransitionError
from src.domain.state_machine import (
    transition_work_order, transition_spare,
)


# ---------- 工单状态机 ----------
@pytest.mark.parametrize("current,action,expected", [
    (W.PENDING_CONFIRMATION, A.CONFIRM, W.PENDING_ASSIGNMENT),
    (W.PENDING_ASSIGNMENT, A.ASSIGN, W.PENDING_ACCEPTANCE),
    (W.PENDING_ACCEPTANCE, A.ASSIGN, W.PENDING_ACCEPTANCE),  # 改派
    (W.PENDING_ACCEPTANCE, A.ACCEPT, W.PENDING_MAINTENANCE),
    (W.PENDING_MAINTENANCE, A.START, W.MAINTAINING),
    (W.MAINTAINING, A.WAIT_FOR_PARTS, W.WAITING_PARTS),
    (W.WAITING_PARTS, A.RESUME, W.MAINTAINING),
    (W.MAINTAINING, A.SUBMIT_FOR_INSPECTION, W.PENDING_INSPECTION),
    (W.PENDING_INSPECTION, A.PASS_INSPECTION, W.COMPLETED),
    (W.PENDING_INSPECTION, A.REJECT_INSPECTION, W.MAINTAINING),
])
def test_work_order_valid_transitions(current, action, expected):
    assert transition_work_order(current, action) == expected


@pytest.mark.parametrize("current,action", [
    (W.COMPLETED, A.CONFIRM),
    (W.CANCELLED, A.CONFIRM),
    (W.PENDING_CONFIRMATION, A.START),
    (W.MAINTAINING, A.ACCEPT),
    (W.WAITING_PARTS, A.SUBMIT_FOR_INSPECTION),
    (W.PENDING_INSPECTION, A.START),
])
def test_work_order_invalid_transitions(current, action):
    with pytest.raises(InvalidTransitionError):
        transition_work_order(current, action)


@pytest.mark.parametrize("current", [
    W.PENDING_CONFIRMATION, W.PENDING_ASSIGNMENT, W.PENDING_ACCEPTANCE,
])
def test_cancel_only_in_early_states(current):
    assert transition_work_order(current, A.CANCEL) == W.CANCELLED


@pytest.mark.parametrize("current", [
    W.PENDING_MAINTENANCE, W.MAINTAINING, W.WAITING_PARTS,
    W.PENDING_INSPECTION, W.COMPLETED, W.CANCELLED,
])
def test_cancel_forbidden_after_accept(current):
    with pytest.raises(InvalidTransitionError):
        transition_work_order(current, A.CANCEL)


# ---------- 备件申请状态机 ----------
@pytest.mark.parametrize("current,action,expected", [
    (S.PENDING_APPROVAL, SA.APPROVE, S.APPROVED),
    (S.PENDING_APPROVAL, SA.REJECT, S.REJECTED),
    (S.APPROVED, SA.RESERVE, S.RESERVED),
    (S.RESERVED, SA.ISSUE, S.ISSUED),
    (S.ISSUED, SA.RETURN, S.PARTIALLY_RETURNED),
    (S.ISSUED, SA.CLOSE, S.CLOSED),
    (S.PARTIALLY_RETURNED, SA.CLOSE, S.CLOSED),
])
def test_spare_valid_transitions(current, action, expected):
    assert transition_spare(current, action) == expected


@pytest.mark.parametrize("current,action", [
    (S.PENDING_APPROVAL, SA.ISSUE),
    (S.APPROVED, SA.ISSUE),
    (S.RESERVED, SA.RETURN),
    (S.CLOSED, SA.APPROVE),
    (S.REJECTED, SA.RESERVE),
    (S.CANCELLED, SA.APPROVE),
])
def test_spare_invalid_transitions(current, action):
    with pytest.raises(InvalidTransitionError):
        transition_spare(current, action)