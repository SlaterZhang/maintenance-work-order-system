"""种子数据：设备档案 + 72 小时遥测历史。

阶段3（预测性维护演示）：种子历史为决定性线性漂移（无随机），
* 演示零准备：打开详情页即见 3 天趋势图，不再空白；
* B 的退化趋势外推有真实历史可算（"预测 X 天后触阈值"）；
* 终点值全部低于满扣阈值，重置后不会自带预警。

阶段4（平台化界面，2026-10-10）：设备从 3 台扩到 8 台，覆盖 4 条产线、
6 种设备类型，使设备台账/看板/大屏的分组视图（按产线、按状态）在重新
播种后即有可展示的分布，不再需要手工造数。

**种子只使用「不隐含其它聚合」的运行状态**：``RUNNING`` / ``STOPPED`` /
``TRIAL_RUNNING``。``MAINTAINING`` 隐含存在维修工单、``WARNING`` 隐含存在
活跃预警，而重置后 B/C 都是空的——播这两种状态会让看板说"维修中"却在
工单列表里找不到单。维修中/预警中的设备由演示流程（注入异常）真实产生。
"""
from datetime import datetime, timedelta, timezone

SEED_EQUIPMENT = [
    {
        "equipment_id": "EQ-000001",
        "name": "一号数控机床",
        "equipment_type": "CNC",
        "production_line_id": "LINE-01",
        "location": "一车间 A 区",
        "manufacturer": "示例机床厂",
        "model": "CNC-X1000",
        "responsible_department": "机加车间",
        "current_status": "RUNNING",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000002",
        "name": "二号加工中心",
        "equipment_type": "MACHINING_CENTER",
        "production_line_id": "LINE-01",
        "location": "一车间 B 区",
        "manufacturer": "示例机床厂",
        "model": "MC-500",
        "responsible_department": "机加车间",
        "current_status": "STOPPED",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000003",
        "name": "三号冷镦机",
        "equipment_type": "COLD_HEADER",
        "production_line_id": "LINE-02",
        "location": "二车间 C 区",
        "manufacturer": "示例标准件厂",
        "model": "CH-200",
        "responsible_department": "标准件车间",
        "current_status": "TRIAL_RUNNING",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000004",
        "name": "四号空压机",
        "equipment_type": "AIR_COMPRESSOR",
        "production_line_id": "LINE-02",
        "location": "二车间 D 区",
        "manufacturer": "示例压缩机厂",
        "model": "AC-75A",
        "responsible_department": "动力车间",
        "current_status": "STOPPED",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000005",
        "name": "五号离心泵",
        "equipment_type": "CENTRIFUGAL_PUMP",
        "production_line_id": "LINE-03",
        "location": "三车间 A 区",
        "manufacturer": "示例泵业",
        "model": "CP-100-32",
        "responsible_department": "动力车间",
        "current_status": "RUNNING",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000006",
        "name": "六号风机",
        "equipment_type": "FAN",
        "production_line_id": "LINE-03",
        "location": "三车间 B 区",
        "manufacturer": "示例风机厂",
        "model": "FJ-4-72",
        "responsible_department": "动力车间",
        "current_status": "RUNNING",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000007",
        "name": "七号传送带",
        "equipment_type": "CONVEYOR",
        "production_line_id": "LINE-04",
        "location": "四车间 A 区",
        "manufacturer": "示例输送设备厂",
        "model": "BC-800",
        "responsible_department": "总装车间",
        "current_status": "TRIAL_RUNNING",
        "enabled": True,
    },
    {
        "equipment_id": "EQ-000008",
        "name": "八号激光切割机",
        "equipment_type": "LASER_CUTTER",
        "production_line_id": "LINE-04",
        "location": "四车间 B 区",
        "manufacturer": "示例激光设备厂",
        "model": "LC-3015",
        "responsible_department": "机加车间",
        "current_status": "RUNNING",
        "enabled": True,
    },
]

HISTORY_HOURS = 72
SEED_SOURCE = "SEED_HISTORY"
SPEED_RPM = 1450.0

# 每台设备的 72 小时缓变基线：(起点, 每小时增量)；i=0 是 72 小时前
# 满扣阈值参照 B 规则引擎：温度 90℃ / 振动 6.0 mm·s⁻¹ / 电流 30A
# 终点值均低于满扣阈值 → 重置后不会自带预警；转速按设备类型给额定值。
SEED_TELEMETRY_PROFILES = {
    # 主轴轴承缓慢劣化：振动、温度持续上行——趋势预测的"主角"
    "EQ-000001": {
        "temperature": (63.0, 0.090),   # 63.00 → 69.39
        "vibration": (2.40, 0.0120),     # 2.400 → 3.252（终点略越 3.0 正常线）
        "current": (11.3, 0.0100),       # 11.30 → 12.01
        "rpm": 1450.0,
    },
    # 平稳设备：几乎无漂移
    "EQ-000002": {
        "temperature": (64.0, 0.020),   # 64.00 → 65.42
        "vibration": (2.20, 0.0050),     # 2.200 → 2.555
        "current": (12.4, 0.0200),      # 12.40 → 13.82
        "rpm": 1450.0,
    },
    # 电流缓慢上行：另一条可讲的预测线索
    "EQ-000003": {
        "temperature": (60.0, 0.030),   # 60.00 → 62.13
        "vibration": (1.80, 0.0100),    # 1.800 → 2.510
        "current": (12.0, 0.0300),      # 12.00 → 14.13
        "rpm": 1450.0,
    },
    # 空压机：停机设备，历史为停机前的低负载记录
    "EQ-000004": {
        "temperature": (52.0, 0.010),   # 52.00 → 52.71
        "vibration": (1.60, 0.0040),    # 1.600 → 1.884
        "current": (9.5, 0.0080),       # 9.50 → 10.07
        "rpm": 980.0,
    },
    # 离心泵：振动偏高但未越满扣线——"待关注但尚未触发预警"的样本
    "EQ-000005": {
        "temperature": (68.0, 0.060),   # 68.00 → 72.26
        "vibration": (4.10, 0.0250),    # 4.100 → 5.875（逼近满扣 6.0）
        "current": (16.2, 0.0200),      # 16.20 → 17.62
        "rpm": 2900.0,
    },
    # 风机：平稳运行
    "EQ-000006": {
        "temperature": (58.0, 0.025),   # 58.00 → 59.78
        "vibration": (2.60, 0.0060),    # 2.600 → 3.026
        "current": (10.8, 0.0150),      # 10.80 → 11.87
        "rpm": 1780.0,
    },
    # 传送带：试运行中——皮带张紧度下降，振动明显上行
    "EQ-000007": {
        "temperature": (66.0, 0.045),   # 66.00 → 69.20
        "vibration": (3.80, 0.0280),    # 3.800 → 5.788（逼近满扣 6.0）
        "current": (13.5, 0.0180),      # 13.50 → 14.78
        "rpm": 420.0,
    },
    # 激光切割机：新设备，状态最好
    "EQ-000008": {
        "temperature": (54.0, 0.015),   # 54.00 → 55.07
        "vibration": (1.40, 0.0030),    # 1.400 → 1.613
        "current": (11.0, 0.0050),      # 11.00 → 11.36
        "rpm": 3400.0,
    },
}


def seed_telemetry(db, now: datetime | None = None) -> int:
    """为每台种子设备补 72 小时历史样本（该设备已有样本则跳过）。

    :returns: 新增样本数。
    """
    from src.domain.models import TelemetryBatch, TelemetrySampleRecord

    if now is None:
        now = datetime.now(timezone.utc)
    created = 0
    for eq in SEED_EQUIPMENT:
        eq_id = eq["equipment_id"]
        existing = (
            db.query(TelemetrySampleRecord)
            .filter(TelemetrySampleRecord.equipment_id == eq_id)
            .count()
        )
        if existing > 0:
            continue
        profile = SEED_TELEMETRY_PROFILES[eq_id]
        speed_rpm = profile.get("rpm", SPEED_RPM)
        db.add(TelemetryBatch(
            batch_id=f"SEED-BATCH-{eq_id}",
            equipment_id=eq_id,
            source=SEED_SOURCE,
            accepted_count=HISTORY_HOURS,
            received_at=now - timedelta(hours=HISTORY_HOURS),
        ))
        for i in range(HISTORY_HOURS):
            measured_at = now - timedelta(hours=HISTORY_HOURS - i)
            db.add(TelemetrySampleRecord(
                sample_id=f"SEED-{eq_id}-{i:03d}",
                equipment_id=eq_id,
                measured_at=measured_at,
                temperature_c=round(profile["temperature"][0]
                                    + profile["temperature"][1] * i, 2),
                vibration_mm_s=round(profile["vibration"][0]
                                     + profile["vibration"][1] * i, 2),
                current_a=round(profile["current"][0]
                                + profile["current"][1] * i, 2),
                rotational_speed_rpm=speed_rpm,
                created_at=measured_at,
            ))
        created += HISTORY_HOURS
    db.commit()
    return created
