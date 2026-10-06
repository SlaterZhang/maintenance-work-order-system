"""阶段3退化趋势外推测试。

覆盖（``domain/trend.py``）：
* 纯函数：上行/平稳/好转/样本不足/已越过阈值；
* 集成：评估响应与 latest 端点携带趋势字段；A 不可达时降级 UNKNOWN；
* 文案：trend_conclusion_zh 的中文结论。
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.domain import trend as trend_engine
from src.interfaces.clients import member_a
from tests.conftest import (
    EQUIPMENT_ID,
    health_body,
    internal_headers,
    sample_payload,
)

EVAL_URL = "/api/v1/health-evaluations"
LATEST_URL = "/api/v1/health-evaluations/latest"


def _now():
    return datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)


def _sample(epoch: datetime, temperature: float = 65.0,
            vibration: float = 2.0, current: float = 12.0) -> dict:
    return {
        "sampleId": str(uuid.uuid4()),
        "measuredAt": epoch.isoformat().replace("+00:00", "Z"),
        "temperatureC": temperature,
        "vibrationMmS": vibration,
        "currentA": current,
        "rotationalSpeedRpm": 1450.0,
    }


def _window(hours: int = 24, **series) -> list[dict]:
    """构造最近 hours 小时逐小时样本，series 为 (起点, 每小时增量)。"""
    merged = {"temperature": (65.0, 0.0), "vibration": (2.0, 0.0),
              "current": (12.0, 0.0)}
    merged.update(series)
    series = merged
    now = _now()
    out = []
    for i in range(hours):
        t = now - timedelta(hours=hours - 1 - i)
        out.append(_sample(
            t,
            temperature=series["temperature"][0] + series["temperature"][1] * i,
            vibration=series["vibration"][0] + series["vibration"][1] * i,
            current=series["current"][0] + series["current"][1] * i,
        ))
    return out


# ---------- 纯函数 ----------
def test_analyze_trend_no_samples():
    result = trend_engine.analyze_trend(None)
    assert result == {
        "trend": "UNKNOWN", "trendMetric": None, "trendRatePerDay": None,
        "predictedDaysToThreshold": None, "trendThreshold": None,
        "trendSampleCount": 0,
    }


def test_analyze_trend_single_sample():
    result = trend_engine.analyze_trend([_sample(_now())])
    assert result["trend"] == "UNKNOWN"
    assert result["trendSampleCount"] == 1


def test_analyze_trend_degrading_rising_temperature():
    # +0.5℃/小时 = 12℃/天；当前 76.5℃，距 90℃ 阈值 13.5℃ → 1.1 天
    result = trend_engine.analyze_trend(
        _window(temperature=(65.0, 0.5)))
    assert result["trend"] == "DEGRADING"
    assert result["trendMetric"] == "temperature"
    assert result["trendRatePerDay"] == 12.0
    assert result["predictedDaysToThreshold"] == 1.1
    assert result["trendThreshold"] == 90.0
    assert result["trendSampleCount"] == 24


def test_analyze_trend_stable_below_noise_band():
    # +0.01℃/小时 = 0.24℃/天，低于 0.5℃/天噪声线 → STABLE
    result = trend_engine.analyze_trend(
        _window(temperature=(65.0, 0.01)))
    assert result["trend"] == "STABLE"
    assert result["trendMetric"] is None
    assert result["predictedDaysToThreshold"] is None


def test_analyze_trend_improving():
    # 所有指标下行 → IMPROVING
    result = trend_engine.analyze_trend(_window(
        temperature=(75.0, -0.5), vibration=(4.0, -0.02), current=(14.0, -0.1)))
    assert result["trend"] == "IMPROVING"
    assert result["predictedDaysToThreshold"] is None


def test_analyze_trend_already_over_threshold_no_prediction():
    # 已越过满扣阈值：不预测（评估等级本身会说明问题）
    result = trend_engine.analyze_trend(
        _window(temperature=(95.0, 0.5)))
    assert result["trend"] == "DEGRADING"
    assert result["trendMetric"] is None
    assert result["predictedDaysToThreshold"] is None


def test_analyze_trend_picks_most_urgent_metric():
    # 振动 +0.05/小时=1.2/天（终点 3.15，距 6.0 → 2.4 天）
    # 温度 +0.5/小时=12/天（终点 76.5，距 90 → 1.1 天）→ 温度更紧迫
    result = trend_engine.analyze_trend(_window(
        temperature=(65.0, 0.5), vibration=(2.0, 0.05)))
    assert result["trendMetric"] == "temperature"
    assert result["predictedDaysToThreshold"] == 1.1


def test_analyze_trend_caps_prediction_horizon():
    # 极缓慢上行：预测超 365 天 → 截断
    result = trend_engine.analyze_trend(
        _window(temperature=(65.0, 0.021)))   # ≈0.5℃/天，距 90℃ 需 50 天
    assert result["trend"] == "DEGRADING"
    assert result["predictedDaysToThreshold"] <= trend_engine.MAX_PREDICTED_DAYS


def test_trend_conclusion_zh():
    result = trend_engine.analyze_trend(_window(temperature=(65.0, 0.5)))
    text = trend_engine.trend_conclusion_zh(result)
    assert text.startswith("趋势预测：温度以约 12.0℃/天")
    assert "预计 1.1 天后" in text
    assert trend_engine.trend_conclusion_zh({"trend": "UNKNOWN"}) == ""


# ---------- 集成：评估响应与 latest 端点 ----------
def test_evaluation_response_carries_trend(client, monkeypatch):
    monkeypatch.setattr(
        member_a, "fetch_recent_telemetry",
        lambda *a, **k: _window(temperature=(65.0, 0.5)))

    body = health_body(sample=sample_payload(
        temperatureC=76.5, vibrationMmS=2.0, currentA=12.0,
        rotationalSpeedRpm=1500.0))
    r = client.post(EVAL_URL, json=body, headers=internal_headers())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["trend"] == "DEGRADING"
    assert data["trendMetric"] == "temperature"
    assert data["predictedDaysToThreshold"] == 1.1
    assert data["trendSampleCount"] == 24

    # latest 端点读档返回同一趋势（轮询零额外调用）
    r2 = client.get(
        f"{LATEST_URL}?equipmentId={EQUIPMENT_ID}",
        headers={"Authorization": "Bearer test-token-USER-B-001",
                 "X-Trace-Id": "trace-trend-latest"})
    assert r2.status_code == 200
    assert r2.json()["trend"] == "DEGRADING"
    assert r2.json()["predictedDaysToThreshold"] == 1.1


def test_evaluation_trend_degrades_gracefully_when_a_unreachable(client):
    """A 不可达 / 历史为空：评估主链路照常成功，趋势降级 UNKNOWN。"""
    body = health_body(sample=sample_payload(
        temperatureC=60.0, vibrationMmS=1.0, currentA=10.0,
        rotationalSpeedRpm=1500.0))
    r = client.post(EVAL_URL, json=body, headers=internal_headers())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["riskLevel"] == "LOW"
    assert data["trend"] == "UNKNOWN"
    assert data["trendMetric"] is None
    assert data["predictedDaysToThreshold"] is None
    assert data["trendSampleCount"] == 0
