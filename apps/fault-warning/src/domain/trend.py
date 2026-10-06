"""退化趋势外推（阶段3：预测性维护）。

基于 A 服务的历史遥测（最近 N 样本）做**逐指标最小二乘线性外推**：
* 指标按当前速率上行且尚未越过满扣阈值 → 预计 N 天后触阈值；
* "最紧迫指标"（预计触阈值天数最小）作为评估结论的头条；
* 样本不足 / A 不可达 → ``UNKNOWN``，所有预测字段为 null——
  趋势是增强信息，**绝不阻塞评估主链路**（P0-1 的教训：附加信息
  失败不能拖垮核心写入）。

阈值口径与 ``scoring.py`` 规则引擎一致（满扣阈值 = 报警终点）：
================ ======== ========
指标               正常      满扣
================ ======== ========
温度 ℃            70       90
振动 mm·s⁻¹       3.0      6.0
电流 A            15       30
================ ======== ========
"""
from __future__ import annotations

# 指标名 → (满扣阈值, 判定为"上行"的最小速率/天)
METRIC_THRESHOLDS: dict[str, float] = {
    "temperature": 90.0,
    "vibration": 6.0,
    "current": 30.0,
}
METRIC_FIELD: dict[str, str] = {
    "temperature": "temperatureC",
    "vibration": "vibrationMmS",
    "current": "currentA",
}
METRIC_LABEL_ZH: dict[str, str] = {
    "temperature": "温度",
    "vibration": "振动",
    "current": "电流",
}
# 参与外推的样本窗口
TREND_WINDOW = 24
# 速率低于该值（单位/天）视为该指标无上行趋势
MIN_RATE_PER_DAY = {
    "temperature": 0.5,
    "vibration": 0.05,
    "current": 0.3,
}
MAX_PREDICTED_DAYS = 365.0
SECONDS_PER_DAY = 86400.0


def _linear_rate_per_day(points: list[tuple[float, float]]) -> float | None:
    """最小二乘斜率（值/天）。points: [(epoch 秒, 值)]，需 ≥2 个且时间跨度 > 0。"""
    n = len(points)
    if n < 2:
        return None
    t0 = points[0][0]
    xs = [(t - t0) / SECONDS_PER_DAY for t, _ in points]
    mean_x = sum(xs) / n
    mean_y = sum(y for _, y in points) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, (_, y) in zip(xs, points))
    return cov / var_x


def _parse_epoch(measured_at: str) -> float | None:
    """解析 RFC 3339 / ISO 8601 时间为 epoch 秒；失败返回 None。"""
    from datetime import datetime

    text = str(measured_at or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def analyze_trend(samples: list[dict] | None) -> dict:
    """对最近样本窗口计算趋势与触阈值预测。

    :param samples: A 服务遥测样本（任意顺序），取 measuredAt 最新的
        ``TREND_WINDOW`` 条参与计算。
    :returns: 契约趋势字段::

            {
              "trend": "DEGRADING" | "STABLE" | "IMPROVING" | "UNKNOWN",
              "trendMetric": "temperature" | ... | None,   # 最紧迫指标
              "trendRatePerDay": float | None,             # 该指标速率（单位/天）
              "predictedDaysToThreshold": float | None,     # 预计 N 天后触满扣阈值
              "trendThreshold": float | None,                # 该指标满扣阈值
              "trendSampleCount": int,                       # 参与计算的样本数
            }
    """
    empty = {
        "trend": "UNKNOWN", "trendMetric": None, "trendRatePerDay": None,
        "predictedDaysToThreshold": None, "trendThreshold": None,
        "trendSampleCount": 0,
    }
    if not samples:
        return empty

    parsed = []
    for s in samples:
        epoch = _parse_epoch(s.get("measuredAt"))
        if epoch is None:
            continue
        parsed.append((epoch, s))
    if len(parsed) < 2:
        return {**empty, "trendSampleCount": len(parsed)}
    parsed.sort(key=lambda p: p[0])
    window = parsed[-TREND_WINDOW:]

    rates: dict[str, float] = {}
    for metric, field in METRIC_FIELD.items():
        points = []
        for epoch, s in window:
            try:
                points.append((epoch, float(s[field])))
            except (KeyError, TypeError, ValueError):
                continue
        rate = _linear_rate_per_day(points)
        if rate is not None:
            rates[metric] = rate

    if not rates:
        return {**empty, "trendSampleCount": len(window)}

    rising = {
        m: r for m, r in rates.items()
        if r >= MIN_RATE_PER_DAY[m]
    }
    declining = {m: r for m, r in rates.items() if r < 0}

    result = {**empty, "trendSampleCount": len(window)}
    if rising:
        result["trend"] = "DEGRADING"
    elif declining and len(declining) == len(rates):
        result["trend"] = "IMPROVING"
    else:
        result["trend"] = "STABLE"

    # 最紧迫指标：上行且尚未越过满扣阈值，取触阈值天数最小者
    best: tuple[float, str, float] | None = None   # (days, metric, rate)
    for metric, rate in rising.items():
        threshold = METRIC_THRESHOLDS[metric]
        current = window[-1][1].get(METRIC_FIELD[metric])
        try:
            current = float(current)
        except (TypeError, ValueError):
            continue
        if current >= threshold:
            continue    # 已越过阈值：无需预测（评估本身会给出等级）
        days = (threshold - current) / rate
        if days < 0:
            continue
        days = min(round(days, 1), MAX_PREDICTED_DAYS)
        if best is None or days < best[0]:
            best = (days, metric, rate)

    if best is not None:
        days, metric, rate = best
        result.update({
            "trendMetric": metric,
            "trendRatePerDay": round(rate, 3),
            "predictedDaysToThreshold": days,
            "trendThreshold": METRIC_THRESHOLDS[metric],
        })
    return result


def trend_conclusion_zh(trend: dict) -> str:
    """把趋势字段渲染为看板/预警文案（中文一句话，无趋势返回空串）。"""
    if not trend or trend.get("trend") == "UNKNOWN":
        return ""
    metric = trend.get("trendMetric")
    days = trend.get("predictedDaysToThreshold")
    rate = trend.get("trendRatePerDay")
    threshold = trend.get("trendThreshold")
    label = METRIC_LABEL_ZH.get(metric or "", "")
    unit = {"temperature": "℃/天", "vibration": "mm·s⁻¹/天", "current": "A/天"}.get(metric or "")
    if trend.get("trend") == "DEGRADING" and metric and days is not None:
        return (f"趋势预测：{label}以约 {rate}{unit} 的速率上行，"
                f"预计 {days} 天后达到 {threshold:g}{'℃' if metric == 'temperature' else ('mm·s⁻¹' if metric == 'vibration' else 'A')}满扣阈值，建议提前安排检修"
                if threshold is not None else "")
    if trend.get("trend") == "DEGRADING":
        return "趋势预测：关键指标持续上行，已越过满扣阈值，建议立即处置"
    if trend.get("trend") == "IMPROVING":
        return "趋势预测：各项指标整体好转（IMPROVING）"
    return "趋势预测：各项指标平稳（STABLE）"
