"""成员 B 的测试夹具。

交付说明
--------
本文件**必须**随代码一起提交。成员 C 的 ``tests/conftest.py`` 未进入版本库，
导致 ``apps/maintenance`` 的四个测试文件（630 行）全部无法运行。
B 侧把夹具一并交付，避免重演同一问题。

外部依赖策略
------------
测试**完全不访问网络**：

* 三个外部客户端（A / C / D）默认由 autouse 夹具替换为受控实现；
* ``ALLOW_CLIENT_MOCK`` 在测试进程内强制为 ``false``，
  任何漏打的桩都会立刻失败，而不是静默返回伪造数据；
* 需要模拟"外部服务不可达"的用例，在测试体内再 monkeypatch 一次即可覆盖。

数据库策略
----------
每个用例使用一个**独立的临时 SQLite 文件**（放在 ``tests/.pytest-data/``，
已被 ``.gitignore`` 忽略），而不是内存库：

* 请求级 Session 与断言用 Session 是**不同连接**，
  既忠实于生产的"每请求一个 Session"，也避免读到旧事务快照；
* 不依赖操作系统临时目录，避开受限环境下临时目录不可写的问题。
"""

import os
import uuid
from pathlib import Path

SCRATCH_DIR = Path(__file__).resolve().parent / ".pytest-data"

# 必须在导入 src.* 之前设置：settings 在模块导入时实例化
os.environ["INTERNAL_API_TOKEN"] = "test-internal-token"
os.environ["ALLOW_CLIENT_MOCK"] = "false"
os.environ["MODEL_VERSION"] = "rule-engine-1.0.0"
# 生产代码在模块导入时就建好了 engine，让 lifespan 的建表落在测试暂存目录，
# 避免在 apps/fault-warning/ 下留下 member_b.db
os.environ["DATABASE_URL"] = (
    f"sqlite:///{(SCRATCH_DIR / 'bootstrap.db').as_posix()}"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.domain.models import Base  # noqa: E402
from src.infrastructure.db import get_db  # noqa: E402
from src.interfaces.clients import member_a, member_c, member_d  # noqa: E402
from src.main import app  # noqa: E402

INTERNAL_TOKEN = "test-internal-token"
USER_ID = "USER-B-001"
TEST_TOKEN_PREFIX = "test-token-"
TRACE_ID = "trace-test-b-0001"

EQUIPMENT_ID = "EQ-000001"
ORDER_ID = "WO-20260917-0001"


# --------------------------------------------------------------------------
# 请求体构造工具
# --------------------------------------------------------------------------
def sample_payload(**overrides) -> dict:
    """契约 ``TelemetrySample``，默认值取 contracts/examples 中的那一条。"""
    payload = {
        "sampleId": str(uuid.uuid4()),
        "measuredAt": "2026-09-17T08:29:50Z",
        "temperatureC": 78.5,
        "vibrationMmS": 6.2,
        "currentA": 13.8,
        "rotationalSpeedRpm": 1450.0,
    }
    payload.update(overrides)
    return payload


def health_body(**overrides) -> dict:
    """契约 ``HealthEvaluationRequest``。"""
    body = {
        "evaluationId": str(uuid.uuid4()),
        "equipmentId": EQUIPMENT_ID,
        "requestedAt": "2026-09-17T08:29:55Z",
        "sample": sample_payload(),
    }
    body.update(overrides)
    return body


def conclusion_event(warning_id: str | None = "WARN-20260917-0001", **overrides) -> dict:
    """契约 ``MaintenanceConclusionEvent``，默认取 examples 中的样例。"""
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": "MaintenanceConclusionReported",
        "schemaVersion": "2.0",
        "occurredAt": "2026-09-17T11:20:00Z",
        "sourceMember": "MEMBER_C",
        "traceId": TRACE_ID,
        "payload": {
            "orderId": ORDER_ID,
            "warningId": warning_id,
            "equipmentId": EQUIPMENT_ID,
            "rootCause": "主轴轴承润滑不足导致振动升高",
            "measures": "补充润滑并更换磨损轴承，完成空载和带载试运行",
            "result": "RECOVERED",
            "completedAt": "2026-09-17T11:18:00Z",
            "effective": True,
            "submittedBy": "USER-C-002",
            "downtimeMinutes": 168,
        },
    }
    payload_overrides = overrides.pop("payload", None)
    if payload_overrides:
        event["payload"].update(payload_overrides)
    event.update(overrides)
    return event


def internal_headers(idempotency_key: str | None = None, **extra) -> dict:
    """服务间调用请求头（C-INT-02 / C-INT-05）。"""
    headers = {
        "X-Internal-Token": INTERNAL_TOKEN,
        "X-Trace-Id": TRACE_ID,
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    headers.update(extra)
    return headers


def user_headers(
    user_id: str = USER_ID,
    idempotency_key: str | None = None,
    **extra,
) -> dict:
    """前端调用请求头（B-API-01 ~ 03）：身份经 D 签发的 Bearer JWT 携带。

    测试令牌约定为 ``test-token-<userId>``，由 ``mock_permissions``
    中的 ``verify_bearer`` 桩解析回用户上下文。
    """
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN_PREFIX}{user_id}",
        "X-Trace-Id": TRACE_ID,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    headers.update(extra)
    return headers


def warning_raised_event(warning_id: str = "WARN-20260917-0001", **overrides) -> dict:
    """契约 ``WarningRaisedEvent``，用于构造已有的预警上下文。"""
    event = {
        "eventId": str(uuid.uuid4()),
        "eventType": "WarningRaised",
        "schemaVersion": "2.0",
        "occurredAt": "2026-09-17T08:30:00Z",
        "sourceMember": "MEMBER_B",
        "traceId": TRACE_ID,
        "payload": {
            "warningId": warning_id,
            "equipmentId": EQUIPMENT_ID,
            "riskLevel": "HIGH",
            "healthScore": 49.4,
            "suspectedFault": "主轴轴承振动异常",
            "recommendedAction": "建议停机检查主轴轴承及润滑状态",
            "warningAt": "2026-09-17T08:29:55Z",
            "modelVersion": "rule-engine-1.0.0",
            "metricSnapshot": sample_payload(),
        },
    }
    payload_overrides = overrides.pop("payload", None)
    if payload_overrides:
        event["payload"].update(payload_overrides)
    event.update(overrides)
    return event


# --------------------------------------------------------------------------
# 数据库夹具
# --------------------------------------------------------------------------
@pytest.fixture()
def db_engine():
    """每个用例一个临时 SQLite 文件库。"""
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    db_path = SCRATCH_DIR / f"test-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture()
def client(session_factory):
    """TestClient：每个请求使用独立 Session，与生产一致。"""

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def db(session_factory):
    """断言用只读会话（独立连接）。

    用例内直接 ``db.query(...)`` 即可；不参与 HTTP 请求的事务。
    """
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------
# 外部依赖桩（默认 autouse，保证用例不触网）
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_equipment(monkeypatch):
    """默认：A 返回一台存在的设备。"""

    def fake_get_equipment(equipment_id: str, trace_id: str) -> dict:
        return {
            "equipmentId": equipment_id,
            "name": f"设备-{equipment_id}",
            "equipmentType": "CNC",
            "productionLineId": "LINE-01",
            "location": "一车间 A 区",
            "responsibleDepartment": "机加车间",
            "currentStatus": "RUNNING",
            "enabled": True,
            "version": 1,
        }

    monkeypatch.setattr(member_a, "get_equipment", fake_get_equipment)
    return fake_get_equipment


@pytest.fixture(autouse=True)
def mock_permissions(monkeypatch):
    """默认：D-API-02 返回具备预警分析员权限的用户上下文。"""

    def fake_get_access_context(user_id: str, trace_id: str) -> dict:
        return {
            "userId": user_id,
            "displayName": "测试预警分析员",
            "roleCodes": ["WARNING_ANALYST"],
            "permissions": [
                "EQUIPMENT_READ",
                "WARNING_READ",
                "WARNING_ACKNOWLEDGE",
            ],
            "organization": "质量管理部",
            "enabled": True,
        }

    def fake_verify_bearer(token: str, trace_id: str) -> dict | None:
        if not token.startswith(TEST_TOKEN_PREFIX):
            return None
        return fake_get_access_context(
            token[len(TEST_TOKEN_PREFIX):], trace_id
        )

    monkeypatch.setattr(member_d, "get_access_context", fake_get_access_context)
    monkeypatch.setattr(member_d, "verify_bearer", fake_verify_bearer)
    return fake_verify_bearer


@pytest.fixture(autouse=True)
def captured_events(monkeypatch):
    """默认：C 正常接收预警，返回 orderId；报文被记录下来供断言。"""
    sent: list[dict] = []

    def fake_send_warning_raised(event: dict, trace_id: str, event_id: str):
        sent.append(event)
        return (
            True,
            {
                "accepted": True,
                "duplicate": False,
                "orderId": ORDER_ID,
                "traceId": trace_id,
            },
            None,
        )

    monkeypatch.setattr(member_c, "send_warning_raised", fake_send_warning_raised)
    return sent


@pytest.fixture(autouse=True)
def captured_notifications(monkeypatch):
    """默认：D 的通知接口返回成功；调用被记录下来供断言。"""
    calls: list[dict] = []

    def fake_submit_notification(
        recipients, template_code, variables, trace_id, idempotency_key
    ):
        calls.append(
            {
                "recipients": list(recipients),
                "templateCode": template_code,
                "variables": dict(variables),
                "traceId": trace_id,
                "idempotencyKey": idempotency_key,
            }
        )
        return True, None

    monkeypatch.setattr(member_d, "submit_notification", fake_submit_notification)
    return calls
