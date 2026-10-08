"""预警状态机（B 模块内部）。

状态取值来自 ``contracts/shared-enums.json`` 的 ``warningStatus``；
动作取值来自模块私有的 :class:`~src.domain.enums.WarningAction`。

状态迁移图
----------

.. code-block:: text

    (新建) ──► OPEN
                 │  ACKNOWLEDGE            ┌──────────────┐
                 ├──────────────► ACKNOWLEDGED ◄───────────┤ HOLD_ACKNOWLEDGED
                 │                    │                    │
                 │ LINK_TO_ORDER      │ LINK_TO_ORDER      │
                 ▼                    ▼                    │
            LINKED_TO_ORDER ◄──────────┘                    │
                 │                                          │
                 ├── RESOLVE ──────────► RESOLVED            │
                 └── MARK_FALSE_POSITIVE ► FALSE_POSITIVE    │
                                                             │
    OPEN / LINKED_TO_ORDER ── HOLD_ACKNOWLEDGED ─────────────┘

结论如何驱动状态（``docs/06`` 第 10 节第 5 条 + 本模块补充决定）
-------------------------------------------------------------
============================================ ==================
维修结论                                     目标状态
============================================ ==================
``RECOVERED`` 且 ``effective=true``           RESOLVED
``RECOVERED`` 且 ``effective=false``          FALSE_POSITIVE
``PARTIALLY_RECOVERED``                       ACKNOWLEDGED
``NOT_RECOVERED``                             状态不变，风险升级一级
============================================ ==================

``docs/06`` 未规定 ``FALSE_POSITIVE`` 的触发条件，只冻结了取值。
本模块的判定是：结论声称已恢复（``RECOVERED``）但明确标注"未生效"
（``effective=false``），说明该次预警并未对应一个被真正修复的故障，
按"标注为误报"处理。该决定记录在 README，属 B 的语义所有权范围。

``AUTO_RESOLVE``（C-INT-09，2026-10-07 新增）
--------------------------------------------
``docs/06`` 只把"闭环"的权力交给了 C 的维修结论（C-INT-05），但演示链路上
"恢复正常数据"走的是 A 的 ``simulate(NORMAL)`` → A 直接调 B 评估，
**不经过 C 的工单流程**。结果是 LOW 评估落库、设备回到 RUNNING，而预警
永远停在 ``LINKED_TO_ORDER``。本模块补充判定：设备最新一次评估回到
``LOW`` 即视为"最新健康事实已证明恢复"，由评估用例自动闭环活跃预警。
判据严格取 ``LOW``（不含 ``MEDIUM``），因为 ``MEDIUM`` 仍属异常。
"""

from .enums import (
    MaintenanceResult,
    WarningAction,
    WarningStatus,
)
from .errors import InvalidStateTransitionError

W = WarningStatus
A = WarningAction

# 动作 -> (允许的来源状态集合, 目标状态)
WARNING_TRANSITIONS: dict[WarningAction, tuple[frozenset[WarningStatus], WarningStatus]] = {
    A.ACKNOWLEDGE: (
        frozenset({W.OPEN}),
        W.ACKNOWLEDGED,
    ),
    # 已经关联工单的预警仍可被分析员确认：保留 LINKED_TO_ORDER
    # （"已建单"是更强的事实），只记录确认人与确认时间。
    A.ACKNOWLEDGE_LINKED: (
        frozenset({W.LINKED_TO_ORDER}),
        W.LINKED_TO_ORDER,
    ),
    A.LINK_TO_ORDER: (
        frozenset({W.OPEN, W.ACKNOWLEDGED}),
        W.LINKED_TO_ORDER,
    ),
    A.RESOLVE: (
        frozenset({W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER}),
        W.RESOLVED,
    ),
    A.MARK_FALSE_POSITIVE: (
        frozenset({W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER}),
        W.FALSE_POSITIVE,
    ),
    A.HOLD_ACKNOWLEDGED: (
        frozenset({W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER}),
        W.ACKNOWLEDGED,
    ),
    # 2026-10-07 新增（C-INT-08 工单取消回流）：活跃预警随工单取消闭环，
    # 解除"已转工单"悬死态，后续异常评估将新建预警并自动建单
    A.ORDER_CANCELLED: (
        frozenset({W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER}),
        W.CANCELLED,
    ),
    # 2026-10-07 新增（C-INT-09 设备恢复自动闭环）：最新遥测评分回到 LOW
    # （人工在注入工作台点"恢复正常数据"，或真实遥测恢复）时，B 依据最新
    # 健康事实闭环仍处活跃态的预警。此前评估用例只建预警、从不闭环，导致
    # LOW 评估落库后预警仍悬在活跃态、前端"当前预警详情"卡片常驻。
    A.AUTO_RESOLVE: (
        frozenset({W.OPEN, W.ACKNOWLEDGED, W.LINKED_TO_ORDER}),
        W.RESOLVED,
    ),
}

# 闭环状态：不再接受任何动作
TERMINAL_STATUSES: frozenset[WarningStatus] = frozenset(
    {W.RESOLVED, W.FALSE_POSITIVE, W.CANCELLED}
)


def transition_warning(
    current: WarningStatus, action: WarningAction
) -> WarningStatus:
    """计算目标状态；非法迁移抛 :class:`InvalidStateTransitionError`。"""
    if action not in WARNING_TRANSITIONS:
        raise InvalidStateTransitionError(f"未知的预警动作：{action}")
    allowed, target = WARNING_TRANSITIONS[action]
    if current not in allowed:
        raise InvalidStateTransitionError(
            f"预警状态 {current.value} 不允许执行 {action.value}"
        )
    return target


def action_for_conclusion(
    result: MaintenanceResult, effective: bool
) -> WarningAction | None:
    """把维修结论映射为状态机动作。

    ``NOT_RECOVERED`` 不对应状态迁移（保持打开并升级风险），返回 ``None``。
    """
    if result is MaintenanceResult.RECOVERED:
        return A.RESOLVE if effective else A.MARK_FALSE_POSITIVE
    if result is MaintenanceResult.PARTIALLY_RECOVERED:
        return A.HOLD_ACKNOWLEDGED
    return None


def acknowledge_action(
    current: WarningStatus, *, already_acknowledged: bool = False
) -> WarningAction:
    """选择"确认预警"应当使用的动作。

    规则
    ----
    1. 已经确认过（``acknowledgedAt`` 非空）-> 拒绝，保证"一条预警只能确认一次"；
    2. 已关联工单 -> :attr:`WarningAction.ACKNOWLEDGE_LINKED`，保留关联状态；
    3. 其余 -> :attr:`WarningAction.ACKNOWLEDGE`（仅 ``OPEN`` 合法）。

    ``docs/06`` 第 14 节的真实链路里，C 收到 ``WarningRaised`` 后会**立即**建单并
    回传 ``orderId``，预警几乎瞬间进入 ``LINKED_TO_ORDER``。若只允许从 ``OPEN``
    确认，B-API-03 在实际联调中将永远无法使用，因此这里必须支持第 2 条。
    """
    if already_acknowledged:
        raise InvalidStateTransitionError("预警已被确认，不能重复确认")
    if current is W.LINKED_TO_ORDER:
        return A.ACKNOWLEDGE_LINKED
    return A.ACKNOWLEDGE
