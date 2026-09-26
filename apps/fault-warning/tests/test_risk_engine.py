from src.config import settings
from src.domain import risk_engine
from src.domain.enums import order_priority_for

THRESHOLDS = {
    "low": settings.low_score_threshold,
    "medium": settings.medium_score_threshold,
    "high": settings.high_score_threshold,
}


def test_normal_sample_is_low():
    result = risk_engine.evaluate(
        {"temperatureC": 65.0, "vibrationMmS": 3.0, "currentA": 10.0}, THRESHOLDS
    )
    assert result["healthScore"] == 100.0
    assert result["riskLevel"] == "LOW"


def test_contract_example_sample_is_high():
    result = risk_engine.evaluate(
        {"temperatureC": 78.5, "vibrationMmS": 6.2, "currentA": 13.8, "rotationalSpeedRpm": 1450},
        THRESHOLDS,
    )
    assert result["healthScore"] == 42.7
    assert result["riskLevel"] == "HIGH"
    assert result["suspectedFault"]
    assert result["recommendedAction"]


def test_extreme_sample_is_critical():
    result = risk_engine.evaluate(
        {"temperatureC": 200.0, "vibrationMmS": 50.0, "currentA": 500.0}, THRESHOLDS
    )
    assert result["healthScore"] == 0.0
    assert result["riskLevel"] == "CRITICAL"


def test_risk_level_maps_to_order_priority():
    assert order_priority_for("LOW") == "P4"
    assert order_priority_for("MEDIUM") == "P3"
    assert order_priority_for("HIGH") == "P2"
    assert order_priority_for("CRITICAL") == "P1"
