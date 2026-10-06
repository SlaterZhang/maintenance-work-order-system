"""阶段1鉴权闭合补漏回归（2026-10-06）：

A-API-01/02/04 三个浏览器端查询端点曾被遗漏（仅 X-Trace-Id 依赖，
任何伪造令牌都能读设备与遥测数据）。本文件锁定修复：
* 设备列表 / 遥测查询：仅 Bearer JWT（浏览器专用）；
* 设备详情：双轨——浏览器 Bearer 或服务间 X-Internal-Token
  （B 评估前档案确认、C 建单前存在性校验都走内部令牌）。
"""
from src.config import settings

LIST_URL = "/api/v1/equipment?pageSize=1"
DETAIL_URL = "/api/v1/equipment/EQ-000001"
TELEMETRY_URL = "/api/v1/equipment/EQ-000001/telemetry?pageSize=1"

INTERNAL_HEADERS = {"X-Internal-Token": settings.internal_api_token}


def test_equipment_list_rejects_forged_token(client):
    r = client.get(LIST_URL, headers={"Authorization": "Basic forged"})
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_equipment_list_rejects_internal_token_only(client):
    """列表是浏览器专用端点：内部令牌不是用户身份。"""
    # 显式覆盖 TestClient 默认 Bearer，确保请求里只有内部令牌
    r = client.get(LIST_URL, headers={
        **INTERNAL_HEADERS, "Authorization": "Basic forged",
    })
    assert r.status_code == 401


def test_telemetry_rejects_forged_token(client):
    r = client.get(TELEMETRY_URL, headers={"Authorization": "Basic forged"})
    assert r.status_code == 401


def test_equipment_detail_accepts_internal_token(client):
    """详情是浏览器/服务共用端点：内部令牌（B、C 调用）必须放行。"""
    r = client.get(DETAIL_URL, headers=INTERNAL_HEADERS)
    assert r.status_code == 200
    assert r.json()["equipmentId"] == "EQ-000001"


def test_equipment_detail_rejects_no_credential(client):
    r = client.get(DETAIL_URL, headers={"Authorization": "Basic forged"})
    assert r.status_code == 401


def test_browser_facing_reads_accept_valid_token(client):
    for url in [LIST_URL, DETAIL_URL, TELEMETRY_URL]:
        r = client.get(url)
        assert r.status_code == 200, f"{url} 合法令牌应放行，实际 {r.status_code}"


def test_x_user_id_header_alone_is_not_credential(client):
    r = client.get(
        LIST_URL,
        headers={
            "Authorization": "Basic forged",
            "X-User-Id": "USER-A-001",
        },
    )
    assert r.status_code == 401
