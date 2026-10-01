"""B 模块的规则评分引擎（``modelVersion = rule-engine-1.0.0``）。

契约约束（``docs/06`` 第 6 节，已冻结，不得自行解释）
---------------------------------------------------
=============== ========== ========== ==========
健康分区间       风险等级    自动建单    工单优先级
=============== ========== ========== ==========
[80, 100]        LOW        否          P4
[60, 80)         MEDIUM     否          P3
[40, 60)         HIGH       是          P2
[0, 40)          CRITICAL   是          P1
=============== ========== ========== ==========

算法
----
健康分从 100 分开始扣减。四个指标各自定义"正常阈值"与"满扣阈值"，
偏离比例 ``ratio = (value - normal) / (full - normal)``：

* ``ratio <= 0``：指标正常，不扣分；
* ``0 < ratio < 1``：按比例扣分 ``weight * ratio``；
* ``ratio >= 1``：扣满该指标权重。

四项权重之和为 100，因此加权扣分后的健康分天然落在 ``[0, 100]``。
扣分权重最大的指标被认定为**疑似故障来源**，用于生成
``suspectedFault`` 与 ``recommendedAction``。

单指标安全下限
--------------
只做加权求和会有一个业务漏洞：任何单项指标的权重都小于 40，
于是一台 249 °C 的设备也只扣 25 分、落在 MEDIUM，**不会触发工单**。
这对工业场景是危险的，因此增加与加权分取小值的严重度上限：

* 任一指标 ``ratio >= 1.0``（进入报警区）-> 健康分不高于 59.9（至少 HIGH）；
* 任一指标 ``ratio >= 1.5``（进入跳闸区）-> 健康分不高于 39.9（至少 CRITICAL）。

上限作用在**健康分**上而不是直接改写风险等级，
保证"健康分 -> 风险等级"始终严格符合契约表格，两者不会自相矛盾。

阈值选取参考 ISO 10816 的振动烈度分区（Class II 设备 4.5 mm/s 报警、
7.1 mm/s 停机），这里取更保守的 3.0 / 6.0 mm/s 作为教学演示阈值。
引擎是纯函数，无随机、无时间依赖（时间由调用方传入），可重复验证。
"""

from dataclasses import dataclass, field

from .enums import RiskLevel

MODEL_VERSION = "rule-engine-1.0.0"

# 四项指标权重，合计 100
WEIGHTS: dict[str, float] = {
    "vibration": 40.0,
    "temperature": 25.0,
    "current": 20.0,
    "speed": 15.0,
}

# 振动速度 mm/s
VIBRATION_NORMAL_MM_S = 3.0
VIBRATION_FULL_MM_S = 6.0

# 温度 摄氏度
TEMPERATURE_NORMAL_C = 70.0
TEMPERATURE_FULL_C = 90.0

# 电流 A
CURRENT_NORMAL_A = 15.0
CURRENT_FULL_A = 30.0

# 转速 r/min：以额定转速的偏离比例衡量
NOMINAL_SPEED_RPM = 1500.0
SPEED_DEVIATION_NORMAL = 0.05
SPEED_DEVIATION_FULL = 0.15

# 健康分 -> 风险等级（契约分段）
LOW_SCORE_FLOOR = 80.0
MEDIUM_SCORE_FLOOR = 60.0
HIGH_SCORE_FLOOR = 40.0

# 单指标严重度上限
ALARM_RATIO = 1.0
TRIP_RATIO = 1.5
ALARM_SCORE_CAP = 59.9
TRIP_SCORE_CAP = 39.9

# 指标 -> 疑似故障描述
_FAULT_BY_METRIC: dict[str, str] = {
    "vibration": "主轴轴承振动异常",
    "temperature": "设备温升异常",
    "current": "驱动电流异常",
    "speed": "转速偏差异常",
}

# 指标 -> 检修对象（用于拼装建议措施）
_SUBJECT_BY_METRIC: dict[str, str] = {
    "vibration": "主轴轴承",
    "temperature": "冷却与润滑系统",
    "current": "驱动与电气回路",
    "speed": "传动与负载侧",
}

_NO_FAULT_TEXT = "未见明显异常特征"

_ACTION_BY_RISK: dict[RiskLevel, str] = {
    RiskLevel.CRITICAL: "建议立即停机检修，并通知维修主管安排紧急处理",
    RiskLevel.HIGH: "建议停机检查{subject}及润滑状态",
    RiskLevel.MEDIUM: "建议加密监测{subject}并安排计划性巡检",
    RiskLevel.LOW: "维持正常监测",
}


@dataclass(frozen=True)
class HealthResult:
    """一次评估的结果。``penalties`` / ``ratios`` 仅供诊断与测试，不进入对外报文。"""

    health_score: float
    risk_level: RiskLevel
    suspected_fault: str
    recommended_action: str
    model_version: str = MODEL_VERSION
    penalties: dict[str, float] = field(default_factory=dict)
    ratios: dict[str, float] = field(default_factory=dict)


def risk_level_from_score(score: float) -> RiskLevel:
    """按契约分段把健康分映射为风险等级。

    >>> risk_level_from_score(80.0).value
    'LOW'
    >>> risk_level_from_score(79.9).value
    'MEDIUM'
    >>> risk_level_from_score(40.0).value
    'HIGH'
    >>> risk_level_from_score(39.9).value
    'CRITICAL'
    """
    if score >= LOW_SCORE_FLOOR:
        return RiskLevel.LOW
    if score >= MEDIUM_SCORE_FLOOR:
        return RiskLevel.MEDIUM
    if score >= HIGH_SCORE_FLOOR:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _raw_ratio(value: float, normal: float, full: float) -> float:
    """未截断的偏离比例；可为负（正常）或大于 1（超出满扣阈值）。"""
    if full <= normal:  # pragma: no cover - 常量配置错误属于编程错误
        raise ValueError(f"满扣阈值必须大于正常阈值：{normal} -> {full}")
    return (value - normal) / (full - normal)


def metric_ratios(sample: dict) -> dict[str, float]:
    """四个指标的**未截断**偏离比例；用于扣分与严重度判定。"""
    temperature = float(sample["temperatureC"])
    vibration = float(sample["vibrationMmS"])
    current = float(sample["currentA"])
    speed = float(sample["rotationalSpeedRpm"])

    speed_deviation = abs(speed - NOMINAL_SPEED_RPM) / NOMINAL_SPEED_RPM

    return {
        "vibration": _raw_ratio(
            vibration, VIBRATION_NORMAL_MM_S, VIBRATION_FULL_MM_S
        ),
        "temperature": _raw_ratio(
            temperature, TEMPERATURE_NORMAL_C, TEMPERATURE_FULL_C
        ),
        "current": _raw_ratio(current, CURRENT_NORMAL_A, CURRENT_FULL_A),
        "speed": _raw_ratio(
            speed_deviation, SPEED_DEVIATION_NORMAL, SPEED_DEVIATION_FULL
        ),
    }


def metric_penalties(sample: dict) -> dict[str, float]:
    """四个指标各自的扣分值（比例截断到 ``[0, 1]`` 后乘以权重）。"""
    ratios = metric_ratios(sample)
    return {
        name: WEIGHTS[name] * min(1.0, max(0.0, ratio))
        for name, ratio in ratios.items()
    }


def _apply_severity_caps(score: float, ratios: dict[str, float]) -> float:
    """单指标进入报警/跳闸区时压低健康分，避免"单项极端却只判 MEDIUM"。"""
    if any(ratio >= TRIP_RATIO for ratio in ratios.values()):
        return min(score, TRIP_SCORE_CAP)
    if any(ratio >= ALARM_RATIO for ratio in ratios.values()):
        return min(score, ALARM_SCORE_CAP)
    return score


def evaluate_sample(sample: dict) -> HealthResult:
    """对一条监测样本评分。

    :param sample: 形如 ``TelemetrySample`` 的字典，必须含
        ``temperatureC`` / ``vibrationMmS`` / ``currentA`` /
        ``rotationalSpeedRpm``。
    :returns: :class:`HealthResult`
    """
    ratios = metric_ratios(sample)
    penalties = metric_penalties(sample)

    weighted_score = 100.0 - sum(penalties.values())
    score = round(
        min(100.0, max(0.0, _apply_severity_caps(weighted_score, ratios))), 1
    )
    risk = risk_level_from_score(score)

    top_metric = max(penalties, key=lambda name: penalties[name])
    if penalties[top_metric] <= 0.0:
        # 全部指标正常：没有可疑来源
        suspected_fault = _NO_FAULT_TEXT
        recommended_action = _ACTION_BY_RISK[RiskLevel.LOW]
    else:
        suspected_fault = _FAULT_BY_METRIC[top_metric]
        recommended_action = _ACTION_BY_RISK[risk].format(
            subject=_SUBJECT_BY_METRIC[top_metric]
        )

    return HealthResult(
        health_score=score,
        risk_level=risk,
        suspected_fault=suspected_fault,
        recommended_action=recommended_action,
        model_version=MODEL_VERSION,
        penalties=penalties,
        ratios=ratios,
    )
