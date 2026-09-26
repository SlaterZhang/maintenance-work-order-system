BASELINES = {"temperatureC": 70.0, "vibrationMmS": 4.5, "currentA": 12.0}
WEIGHTS = {"temperatureC": 3.0, "vibrationMmS": 15.0, "currentA": 3.5}

FAULT_HINTS = {
    "temperatureC": ("主轴温度过高，疑似冷却或润滑异常", "建议停机检查冷却系统与润滑状态"),
    "vibrationMmS": ("主轴轴承振动异常", "建议停机检查主轴轴承及润滑状态"),
    "currentA": ("电机电流异常升高", "建议检查电机负载与传动机构"),
}

NORMAL_HINT = ("指标正常", "继续保持例行巡检")


def evaluate(sample: dict, thresholds: dict) -> dict:
    penalties = {
        key: max(0.0, float(sample.get(key, 0.0)) - baseline) * WEIGHTS[key]
        for key, baseline in BASELINES.items()
    }
    total = sum(penalties.values())
    score = max(0.0, round(100.0 - total, 1))

    if score >= thresholds["low"]:
        level = "LOW"
    elif score >= thresholds["medium"]:
        level = "MEDIUM"
    elif score >= thresholds["high"]:
        level = "HIGH"
    else:
        level = "CRITICAL"

    if total <= 0:
        fault, action = NORMAL_HINT
    else:
        dominant = max(penalties, key=lambda key: penalties[key])
        fault, action = FAULT_HINTS[dominant]

    return {
        "healthScore": score,
        "riskLevel": level,
        "suspectedFault": fault,
        "recommendedAction": action,
    }
