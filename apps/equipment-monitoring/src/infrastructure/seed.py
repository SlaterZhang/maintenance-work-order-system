"""种子数据：设备档案 + 72 小时遥测历史。

阶段3（预测性维护演示）：种子历史为决定性线性漂移（无随机），
* 演示零准备：打开详情页即见 3 天趋势图，不再空白；
* B 的退化趋势外推有真实历史可算（"预测 X 天后触阈值"）；
* 终点值全部低于满扣阈值，重置后不会自带预警。
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
]

HISTORY_HOURS = 72
SEED_SOURCE = "SEED_HISTORY"
SPEED_RPM = 1450.0

# 每台设备的 72 小时缓变基线：(起点, 每小时增量)；i=0 是 72 小时前
# 满扣阈值参照 B 规则引擎：温度 90℃ / 振动 6.0 mm·s⁻¹ / 电流 30A
SEED_TELEMETRY_PROFILES = {
    # 主轴轴承缓慢劣化：振动、温度持续上行——趋势预测的"主角"
    "EQ-000001": {
        "temperature": (63.0, 0.090),   # 63.00 → 69.39
        "vibration": (2.40, 0.0120),     # 2.400 → 3.252（终点略越 3.0 正常线）
        "current": (11.3, 0.0100),       # 11.30 → 12.01
    },
    # 平稳设备：几乎无漂移
    "EQ-000002": {
        "temperature": (64.0, 0.020),   # 64.00 → 65.42
        "vibration": (2.20, 0.0050),     # 2.200 → 2.555
        "current": (12.4, 0.0200),      # 12.40 → 13.82
    },
    # 电流缓慢上行：另一条可讲的预测线索
    "EQ-000003": {
        "temperature": (60.0, 0.030),   # 60.00 → 62.13
        "vibration": (1.80, 0.0100),    # 1.800 → 2.510
        "current": (12.0, 0.0300),      # 12.00 → 14.13
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
                rotational_speed_rpm=SPEED_RPM,
                created_at=measured_at,
            ))
        created += HISTORY_HOURS
    db.commit()
    return created
