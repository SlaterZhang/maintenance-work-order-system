"""规则评分引擎单元测试。

覆盖：
* 契约冻结的"健康分 -> 风险等级"分段边界；
* 四个指标各自的线性扣分与满扣；
* 疑似故障来源的选取；
* 输出范围与可重复性。
"""

import pytest

from src.domain.enums import RiskLevel
from src.domain.scoring import (
    CURRENT_FULL_A,
    CURRENT_NORMAL_A,
    MODEL_VERSION,
    TEMPERATURE_FULL_C,
    TEMPERATURE_NORMAL_C,
    VIBRATION_FULL_MM_S,
    VIBRATION_NORMAL_MM_S,
    WEIGHTS,
    evaluate_sample,
    metric_penalties,
    risk_level_from_score,
)

NOMINAL = {
    "sampleId": "e51d94ca-5258-4e5a-bccc-99c55cfda001",
    "measuredAt": "2026-09-17T08:29:50Z",
    "temperatureC": 60.0,
    "vibrationMmS": 1.0,
    "currentA": 10.0,
    "rotationalSpeedRpm": 1500.0,
}


def sample(**overrides) -> dict:
    data = dict(NOMINAL)
    data.update(overrides)
    return data


# ---------- 权重与契约分段 ----------
def test_weights_sum_to_one_hundred():
    """四项权重之和必须为 100，否则健康分无法落在 [0, 100]。"""
    assert sum(WEIGHTS.values()) == 100.0


@pytest.mark.parametrize(
    "score,expected",
    [
        (100.0, RiskLevel.LOW),
        (80.0, RiskLevel.LOW),          # 闭区间下界
        (79.9, RiskLevel.MEDIUM),       # 上界开区间
        (60.0, RiskLevel.MEDIUM),
        (59.9, RiskLevel.HIGH),
        (40.0, RiskLevel.HIGH),
        (39.9, RiskLevel.CRITICAL),
        (0.0, RiskLevel.CRITICAL),
    ],
)
def test_risk_level_segments_match_contract(score, expected):
    """docs/06 第 6 节的分段是冻结的，边界值必须精确。"""
    assert risk_level_from_score(score) is expected


# ---------- 扣分规则 ----------
def test_nominal_sample_scores_full_marks():
    result = evaluate_sample(sample())
    assert result.health_score == 100.0
    assert result.risk_level is RiskLevel.LOW
    assert result.penalties == {
        "vibration": 0.0,
        "temperature": 0.0,
        "current": 0.0,
        "speed": 0.0,
    }


def test_metric_at_normal_threshold_does_not_deduct():
    """恰好等于正常阈值不扣分。"""
    penalties = metric_penalties(
        sample(
            vibrationMmS=VIBRATION_NORMAL_MM_S,
            temperatureC=TEMPERATURE_NORMAL_C,
            currentA=CURRENT_NORMAL_A,
        )
    )
    assert penalties["vibration"] == 0.0
    assert penalties["temperature"] == 0.0
    assert penalties["current"] == 0.0


def test_metric_at_full_threshold_deducts_full_weight():
    """达到满扣阈值扣满权重。"""
    penalties = metric_penalties(
        sample(
            vibrationMmS=VIBRATION_FULL_MM_S,
            temperatureC=TEMPERATURE_FULL_C,
            currentA=CURRENT_FULL_A,
        )
    )
    assert penalties["vibration"] == WEIGHTS["vibration"]
    assert penalties["temperature"] == WEIGHTS["temperature"]
    assert penalties["current"] == WEIGHTS["current"]


def test_metric_beyond_full_threshold_is_clamped():
    """超过满扣阈值不会扣穿，健康分不得为负。"""
    result = evaluate_sample(
        sample(
            vibrationMmS=199.0,
            temperatureC=249.0,
            currentA=9999.0,
            rotationalSpeedRpm=100000.0,
        )
    )
    assert result.health_score == 0.0
    assert result.risk_level is RiskLevel.CRITICAL


def test_score_is_monotonic_in_vibration():
    """振动越大，健康分不增。"""
    scores = [
        evaluate_sample(sample(vibrationMmS=value)).health_score
        for value in (1.0, 3.0, 4.0, 5.0, 6.0)
    ]
    assert scores == sorted(scores, reverse=True)


def test_speed_deviation_deducts_when_far_from_nominal():
    """转速偏离额定值会扣分（额定 1500 r/min）。"""
    penalties = metric_penalties(sample(rotationalSpeedRpm=1200.0))
    assert penalties["speed"] == WEIGHTS["speed"]

    penalties = metric_penalties(sample(rotationalSpeedRpm=1500.0))
    assert penalties["speed"] == 0.0


# ---------- 疑似故障来源 ----------
def test_contract_example_sample_yields_high_and_bearing_fault():
    """契约 examples/warning-raised.json 的样本：HIGH + 主轴轴承振动异常。"""
    result = evaluate_sample(
        sample(
            temperatureC=78.5,
            vibrationMmS=6.2,
            currentA=13.8,
            rotationalSpeedRpm=1450.0,
        )
    )
    assert result.risk_level is RiskLevel.HIGH
    assert result.suspected_fault == "主轴轴承振动异常"
    assert result.recommended_action == "建议停机检查主轴轴承及润滑状态"
    assert 40.0 <= result.health_score < 60.0


def test_dominant_metric_determines_suspected_fault():
    """温度主导时疑似故障应指向温升，而不是固定返回轴承问题。"""
    result = evaluate_sample(
        sample(temperatureC=95.0, vibrationMmS=1.0, currentA=1.0)
    )
    assert result.suspected_fault == "设备温升异常"
    assert "冷却与润滑系统" in result.recommended_action


def test_no_anomaly_reports_placeholder_fault():
    result = evaluate_sample(sample())
    assert result.suspected_fault == "未见明显异常特征"
    assert result.recommended_action == "维持正常监测"


# ---------- 其他性质 ----------
def test_model_version_is_reported():
    assert evaluate_sample(sample()).model_version == MODEL_VERSION


def test_evaluation_is_repeatable():
    """纯函数：同样输入必须得到同样输出。"""
    data = sample(vibrationMmS=5.5, temperatureC=80.0)
    first = evaluate_sample(data)
    second = evaluate_sample(data)
    assert first == second


def test_score_always_within_contract_range():
    """健康分必须始终落在契约要求的 [0, 100]。"""
    for vibration in (0.0, 3.0, 6.0, 50.0, 200.0):
        for temperature in (-50.0, 70.0, 90.0, 250.0):
            score = evaluate_sample(
                sample(vibrationMmS=vibration, temperatureC=temperature)
            ).health_score
            assert 0.0 <= score <= 100.0
