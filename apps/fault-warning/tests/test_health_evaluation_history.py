"""B-API-04 健康评估历史查询接口测试。

覆盖：鉴权、按设备/风险等级过滤、分页、契约字段完整性、降序。
"""

import pytest

from src.interfaces.clients import member_d
from tests.conftest import (
    EQUIPMENT_ID,
    USER_ID,
    health_body,
    internal_headers,
    sample_payload,
    user_headers,
)

LIST_URL = "/api/v1/health-evaluations"
POST_URL = "/api/v1/health-evaluations"

NOMINAL_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=1.0, currentA=10.0, rotationalSpeedRpm=1500.0
)
HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)
CRITICAL_SAMPLE = dict(
    temperatureC=249.0, vibrationMmS=199.0, currentA=9999.0,
    rotationalSpeedRpm=100000.0,
)


def _evaluate(client, sample, equipment_id=EQUIPMENT_ID) -> dict:
    body = health_body(
        equipmentId=equipment_id, sample=sample_payload(**sample)
    )
    response = client.post(POST_URL, json=body, headers=internal_headers())
    assert response.status_code == 200, response.text
    return response.json()


def test_requires_login_identity(client):
    """未携带 Bearer 令牌 -> 401。"""
    response = client.get(LIST_URL)
    assert response.status_code == 401, response.text


def test_lists_newest_first(client):
    """按 evaluatedAt 降序返回，最新一条排在最前。"""
    first = _evaluate(client, NOMINAL_SAMPLE)
    second = _evaluate(client, CRITICAL_SAMPLE)

    response = client.get(LIST_URL, headers=user_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["pageSize"] == 20
    assert body["totalPages"] == 1
    assert [item["evaluationId"] for item in body["items"]] == [
        second["evaluationId"],
        first["evaluationId"],
    ]


def test_contract_fields_complete(client):
    """每条记录须含契约 HealthEvaluationResponse 的全部字段。"""
    _evaluate(client, CRITICAL_SAMPLE)
    item = client.get(LIST_URL, headers=user_headers()).json()["items"][0]

    expected = {
        "evaluationId", "equipmentId", "healthScore", "riskLevel",
        "suspectedFault", "recommendedAction", "modelVersion",
        "evaluatedAt", "warningId", "trend", "trendMetric",
        "trendRatePerDay", "predictedDaysToThreshold", "trendThreshold",
        "trendSampleCount",
    }
    assert expected <= set(item)
    assert item["riskLevel"] == "CRITICAL"
    assert item["warningId"]


def test_filters_by_equipment(client):
    """equipmentId 过滤只返回该设备记录。"""
    _evaluate(client, NOMINAL_SAMPLE, equipment_id="EQ-000001")
    _evaluate(client, NOMINAL_SAMPLE, equipment_id="EQ-000002")

    body = client.get(
        f"{LIST_URL}?equipmentId=EQ-000002", headers=user_headers()
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["equipmentId"] == "EQ-000002"


def test_filters_by_risk_level(client):
    """riskLevel 过滤只返回该等级记录。"""
    _evaluate(client, NOMINAL_SAMPLE)      # LOW
    _evaluate(client, CRITICAL_SAMPLE)     # CRITICAL

    low = client.get(f"{LIST_URL}?riskLevel=LOW", headers=user_headers()).json()
    assert low["total"] == 1
    assert low["items"][0]["riskLevel"] == "LOW"

    crit = client.get(
        f"{LIST_URL}?riskLevel=CRITICAL", headers=user_headers()
    ).json()
    assert crit["total"] == 1
    assert crit["items"][0]["riskLevel"] == "CRITICAL"


def test_pagination_slices_results(client):
    """分页切片正确，total 为全量计数。"""
    for _ in range(3):
        _evaluate(client, NOMINAL_SAMPLE)

    page1 = client.get(
        f"{LIST_URL}?page=1&pageSize=2", headers=user_headers()
    ).json()
    page2 = client.get(
        f"{LIST_URL}?page=2&pageSize=2", headers=user_headers()
    ).json()

    assert page1["total"] == 3 and page1["totalPages"] == 2
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 1
    ids = {i["evaluationId"] for i in page1["items"]}
    assert page2["items"][0]["evaluationId"] not in ids


def test_empty_result_is_well_formed(client):
    """无记录时返回空列表而非报错，字段齐全。"""
    body = client.get(LIST_URL, headers=user_headers()).json()
    assert body == {
        "items": [], "page": 1, "pageSize": 20, "total": 0, "totalPages": 0,
    }


def test_rejects_bad_paging(client):
    """page/pageSize 越界 -> 400 VALIDATION_ERROR（服务端把 422 改写为契约口径）。"""
    for query in ("page=0", "pageSize=101"):
        response = client.get(f"{LIST_URL}?{query}", headers=user_headers())
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "VALIDATION_ERROR"


def test_visible_to_any_logged_in_role(client):
    """评估历史不做 WARNING_READ 门禁：无该权限的角色同样可读。"""
    _evaluate(client, NOMINAL_SAMPLE)
    headers = user_headers(user_id="USER-C-004")   # 验收员，无 WARNING_READ
    response = client.get(LIST_URL, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
