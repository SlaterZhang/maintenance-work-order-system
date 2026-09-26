"""C 模块（维修工单/备件）测试夹具。

测试数据对齐产品愿景文档 docs/工业设备智能运维与预测性维护系统.md：
- 第十章演示叙事：EQ-000001 数控机床 CNC-001（LINE-01）主轴轴承振动异常，
  温度92/振动8.5/电流18.2 → 健康度42 → 高风险 → 预警自动建单；
- 事件结构对照 contracts/examples/warning-raised.json（schemaVersion "2.0"）；
- 权限码对照 contracts/openapi.yaml 的 PermissionCode 全集。
"""
import os
import tempfile
from pathlib import Path

# 独立测试库（必须在 import src 之前设置），避免污染 ./member_c.db；
# 直接赋值而非 setdefault，防止外部环境变量把测试引向真实数据库。
_TEST_DB = (Path(tempfile.gettempdir()) / "member_c_test.db").as_posix()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.domain.models import Base
from src.infrastructure.db import SessionLocal, engine
from src.interfaces.clients.member_a import MemberAClient
from src.interfaces.clients.member_b import MemberBClient
from src.interfaces.clients.member_d import MemberDClient

INTERNAL_TOKEN = settings.internal_api_token

# 文档第十章演示设备：LINE-01 产线数控机床
EQUIPMENT_CATALOG = {
    "EQ-000001": "数控机床 CNC-001",
    "EQ-000002": "数控机床 CNC-002",
}


def _mock_equipment(equipment_id: str) -> dict:
    """对照 contracts/openapi.yaml 的 EquipmentDetail 结构。"""
    return {
        "equipmentId": equipment_id,
        "name": EQUIPMENT_CATALOG.get(equipment_id, f"设备-{equipment_id}"),
        "equipmentType": "CNC",
        "productionLineId": "LINE-01",
        "location": "一车间 A 区",
        "manufacturer": None,
        "model": None,
        "responsibleDepartment": "机加车间",
        "currentStatus": "RUNNING",
        "enabled": True,
        "version": 1,
        "createdAt": "2026-09-01T00:00:00Z",
        "updatedAt": "2026-09-01T00:00:00Z",
    }


def warning_event_payload(
    event_id: str = "11111111-1111-1111-1111-111111111111",
    warning_id: str = "WARN-20260917-0001",
    risk: str = "HIGH",
) -> dict:
    """WarningRaised 事件，结构对照 contracts/examples/warning-raised.json。

    缺省值对齐文档第十章演示场景：温度92/振动8.5/电流18.2 → 健康度42
    → 高风险（suspectedFault 主轴轴承振动异常）；严重场景传 risk="CRITICAL"
    （对应"设备变红 → 生成严重预警 → 自动生成维修工单"）。
    """
    return {
        "eventId": event_id,
        "eventType": "WarningRaised",
        "schemaVersion": "2.0",
        "occurredAt": "2026-09-17T08:30:00Z",
        "sourceMember": "MEMBER_B",
        "traceId": "trace-20260917-001",
        "payload": {
            "warningId": warning_id,
            "equipmentId": "EQ-000001",
            "riskLevel": risk,
            "healthScore": 42,
            "suspectedFault": "主轴轴承振动异常",
            "recommendedAction": "建议停机检查主轴轴承及润滑状态",
            "warningAt": "2026-09-17T08:29:55Z",
            "modelVersion": "rule-engine-1.0.0",
            "metricSnapshot": {
                "sampleId": "e51d94ca-5258-4e5a-bccc-99c55cfda001",
                "measuredAt": "2026-09-17T08:29:50Z",
                "temperatureC": 92.0,
                "vibrationMmS": 8.5,
                "currentA": 18.2,
                "rotationalSpeedRpm": 1450,
            },
        },
    }


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from src.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def mock_equipment(monkeypatch):
    """打桩 C-INT-01：查设备（MemberAClient.get_equipment 为 staticmethod）。"""
    def fake_get_equipment(equipment_id, trace_id):
        return _mock_equipment(equipment_id)

    monkeypatch.setattr(
        MemberAClient, "get_equipment", staticmethod(fake_get_equipment),
    )


@pytest.fixture()
def mock_permissions(monkeypatch):
    """打桩 C-INT-06：权限上下文，permissions 覆盖契约 PermissionCode 全集。"""
    def fake_get_access_context(user_id, trace_id):
        return {
            "userId": user_id,
            "displayName": "Mock 维修主管",
            "roleCodes": ["MAINTENANCE_SUPERVISOR"],
            "permissions": [
                "WORK_ORDER_READ", "WORK_ORDER_CREATE",
                "WORK_ORDER_CONFIRM", "WORK_ORDER_ASSIGN",
                "WORK_ORDER_ACCEPT", "WORK_ORDER_MAINTAIN",
                "WORK_ORDER_INSPECT", "WORK_ORDER_CANCEL",
                "SPARE_READ", "SPARE_REQUEST",
                "SPARE_APPROVE", "SPARE_ISSUE",
            ],
            "organization": "机加车间",
            "enabled": True,
        }

    monkeypatch.setattr(
        MemberDClient, "get_access_context",
        staticmethod(fake_get_access_context),
    )


@pytest.fixture()
def captured_status_events(monkeypatch):
    """打桩 C-INT-04：通知 A 设备状态，收集 payload，post 返回 True。"""
    events: list[dict] = []

    def fake_notify_equipment_status(order_id, equipment_id, target_status,
                                     operator_id, reason, trace_id):
        events.append({
            "orderId": order_id,
            "equipmentId": equipment_id,
            "targetStatus": target_status,
            "operatorId": operator_id,
            "reason": reason,
        })
        return True

    monkeypatch.setattr(
        MemberAClient, "notify_equipment_status",
        staticmethod(fake_notify_equipment_status),
    )
    return events


@pytest.fixture()
def captured_conclusions(monkeypatch):
    """打桩 C-INT-05：维修结论回传 B，收集 payload，post 返回 True。"""
    conclusions: list[dict] = []

    def fake_send_conclusion(order_id, warning_id, equipment_id,
                             root_cause, measures, result,
                             completed_at, effective, submitted_by,
                             trace_id):
        conclusions.append({
            "orderId": order_id,
            "warningId": warning_id,
            "equipmentId": equipment_id,
            "rootCause": root_cause,
            "measures": measures,
            "result": result,
            "completedAt": (
                completed_at.isoformat()
                if hasattr(completed_at, "isoformat") else completed_at
            ),
            "effective": effective,
            "submittedBy": submitted_by,
        })
        return True

    monkeypatch.setattr(
        MemberBClient, "send_conclusion",
        staticmethod(fake_send_conclusion),
    )
    return conclusions
