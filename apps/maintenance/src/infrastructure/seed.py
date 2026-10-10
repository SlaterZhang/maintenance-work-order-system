"""种子数据：备件主数据。

阶段4（平台化界面，2026-10-10）：备件此前完全没有种子，C-API-05 查询恒为空，
备件库存页与工单备件申请在重置后的演示库中都是空表。

与 A 的设备种子、D 的身份种子同类，备件属**主数据**（不是业务流水），
因此随服务启动落库、且仅在表为空时补齐；业务流水（申请单、库存事务、
工单）仍保持空，由演示流程真实产生。

编号遵循契约 SparePartId 模式 ``^SP-[0-9]{6}$``。
``reserved_quantity`` 一律为 0：预留量只应由真实的 RESERVE 事务累加。
"""
SEED_SPARE_PARTS = [
    {
        "spare_part_id": "SP-000001",
        "name": "主轴轴承",
        "specification": "6208-2RS",
        "unit": "个",
        "on_hand_quantity": 42,
        "reserved_quantity": 0,
        "reorder_point": 20,
    },
    {
        "spare_part_id": "SP-000002",
        "name": "同步带",
        "specification": "HTD-5M-15",
        "unit": "条",
        "on_hand_quantity": 8,
        "reserved_quantity": 0,
        "reorder_point": 15,      # 低于安全库存：库存告警演示点
    },
    {
        "spare_part_id": "SP-000003",
        "name": "振动传感器",
        "specification": "VS-200",
        "unit": "只",
        "on_hand_quantity": 16,
        "reserved_quantity": 0,
        "reorder_point": 6,
    },
    {
        "spare_part_id": "SP-000004",
        "name": "润滑脂",
        "specification": "EP-2 2kg",
        "unit": "桶",
        "on_hand_quantity": 64,
        "reserved_quantity": 0,
        "reorder_point": 30,
    },
    {
        "spare_part_id": "SP-000005",
        "name": "交流接触器",
        "specification": "CJX2-2510",
        "unit": "个",
        "on_hand_quantity": 4,
        "reserved_quantity": 0,
        "reorder_point": 10,      # 低于安全库存
    },
    {
        "spare_part_id": "SP-000006",
        "name": "密封圈",
        "specification": "NBR-45",
        "unit": "只",
        "on_hand_quantity": 120,
        "reserved_quantity": 0,
        "reorder_point": 40,
    },
    {
        "spare_part_id": "SP-000007",
        "name": "变频器",
        "specification": "VFD-7K5",
        "unit": "台",
        "on_hand_quantity": 2,
        "reserved_quantity": 0,
        "reorder_point": 3,       # 低于安全库存
    },
    {
        "spare_part_id": "SP-000008",
        "name": "冷却液",
        "specification": "XL-20L",
        "unit": "桶",
        "on_hand_quantity": 28,
        "reserved_quantity": 0,
        "reorder_point": 12,
    },
]


def seed_spare_parts(db) -> int:
    """备件主数据仅在表为空时落库，返回新增条数。

    幂等：已有任意备件即整体跳过，避免重复插入或覆盖人工调整过的库存。
    """
    from src.domain.models import SparePart

    if db.query(SparePart).count() > 0:
        return 0
    for item in SEED_SPARE_PARTS:
        db.add(SparePart(**item))
    db.commit()
    return len(SEED_SPARE_PARTS)
