from .enums import WorkOrderAction, WorkOrderStatus
from .errors import InvalidTransitionError

W = WorkOrderStatus
A = WorkOrderAction

# 契约 action -> (允许源状态集合, 目标状态)
WORK_ORDER_TRANSITIONS: dict[A, tuple[set[W], W]] = {
    A.CONFIRM: (
        {W.PENDING_CONFIRMATION},
        W.PENDING_ASSIGNMENT,
    ),
    A.ASSIGN: (
        {W.PENDING_ASSIGNMENT, W.PENDING_ACCEPTANCE},  # 允许改派
        W.PENDING_ACCEPTANCE,
    ),
    A.ACCEPT: (
        {W.PENDING_ACCEPTANCE},
        W.PENDING_MAINTENANCE,
    ),
    A.START: (
        {W.PENDING_MAINTENANCE},
        W.MAINTAINING,
    ),
    A.WAIT_FOR_PARTS: (
        {W.MAINTAINING},
        W.WAITING_PARTS,
    ),
    A.RESUME: (
        {W.WAITING_PARTS},
        W.MAINTAINING,
    ),
    A.SUBMIT_FOR_INSPECTION: (
        {W.MAINTAINING},
        W.PENDING_INSPECTION,
    ),
    A.PASS_INSPECTION: (
        {W.PENDING_INSPECTION},
        W.COMPLETED,
    ),
    A.REJECT_INSPECTION: (
        {W.PENDING_INSPECTION},
        W.MAINTAINING,
    ),
    A.CANCEL: (
        {W.PENDING_CONFIRMATION, W.PENDING_ASSIGNMENT, W.PENDING_ACCEPTANCE},
        W.CANCELLED,
    ),
}

# action -> 所需权限（与契约 PermissionCode 对齐）
ACTION_PERMISSION: dict[A, str] = {
    A.CONFIRM: "WORK_ORDER_CONFIRM",
    A.ASSIGN: "WORK_ORDER_ASSIGN",
    A.ACCEPT: "WORK_ORDER_ACCEPT",
    A.START: "WORK_ORDER_MAINTAIN",
    A.WAIT_FOR_PARTS: "WORK_ORDER_MAINTAIN",
    A.RESUME: "WORK_ORDER_MAINTAIN",
    A.SUBMIT_FOR_INSPECTION: "WORK_ORDER_MAINTAIN",
    A.PASS_INSPECTION: "WORK_ORDER_INSPECT",
    A.REJECT_INSPECTION: "WORK_ORDER_INSPECT",
    A.CANCEL: "WORK_ORDER_CANCEL",
}

# 备件申请状态机
S = __import__("src.domain.enums", fromlist=["SpareRequestStatus"]).SpareRequestStatus
SA = __import__("src.domain.enums", fromlist=["SpareRequestAction"]).SpareRequestAction

SPARE_TRANSITIONS: dict[SA, tuple[set[S], S]] = {
    SA.APPROVE: ({S.PENDING_APPROVAL}, S.APPROVED),
    SA.REJECT: ({S.PENDING_APPROVAL}, S.REJECTED),
    SA.RESERVE: ({S.APPROVED}, S.RESERVED),
    SA.ISSUE: ({S.RESERVED}, S.ISSUED),
    SA.RETURN: ({S.ISSUED}, S.PARTIALLY_RETURNED),
    SA.CLOSE: ({S.ISSUED, S.PARTIALLY_RETURNED}, S.CLOSED),
    SA.CANCEL: (
        {S.PENDING_APPROVAL, S.APPROVED, S.RESERVED},
        S.CANCELLED,
    ),
}

SPARE_ACTION_PERMISSION: dict[SA, str] = {
    SA.APPROVE: "SPARE_APPROVE",
    SA.REJECT: "SPARE_APPROVE",
    SA.RESERVE: "SPARE_APPROVE",
    SA.ISSUE: "SPARE_ISSUE",
    SA.RETURN: "SPARE_ISSUE",
    SA.CLOSE: "SPARE_ISSUE",
    SA.CANCEL: "SPARE_APPROVE",
}


def transition_work_order(current: WorkOrderStatus,
                          action: WorkOrderAction) -> WorkOrderStatus:
    if action not in WORK_ORDER_TRANSITIONS:
        raise InvalidTransitionError(f"未知 action: {action}")
    allowed, target = WORK_ORDER_TRANSITIONS[action]
    if current not in allowed:
        raise InvalidTransitionError(
            f"当前状态 {current.value} 不允许执行 {action.value}"
        )
    return target


def transition_spare(current, action):
    if action not in SPARE_TRANSITIONS:
        raise InvalidTransitionError(f"未知 action: {action}")
    allowed, target = SPARE_TRANSITIONS[action]
    if current not in allowed:
        raise InvalidTransitionError(
            f"备件申请状态 {current.value} 不允许执行 {action.value}"
        )
    return target