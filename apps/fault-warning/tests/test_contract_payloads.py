"""对外报文与 ``contracts/`` 契约的机器可校验一致性。

对应 Wave 2 任务书验收条件：

    "发送的 WarningRaised 报文与 contracts/examples/warning-raised.json
    结构一致，能通过 warning-raised.payload.schema.json 校验"

这些用例直接读取仓库根目录的 ``contracts/``，因此契约一旦漂移会立刻失败，
而不是各模块悄悄维护两套定义。
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from src.domain.enums import ACTIONABLE_RISK_LEVELS, RiskLevel, WarningStatus
from src.domain.scoring import evaluate_sample
from tests.conftest import health_body, internal_headers, sample_payload

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "contracts"
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"

EVAL_URL = "/api/v1/health-evaluations"

ENVELOPE_SCHEMA = SCHEMAS / "event-envelope.schema.json"
WARNING_PAYLOAD_SCHEMA = SCHEMAS / "warning-raised.payload.schema.json"
CONCLUSION_PAYLOAD_SCHEMA = SCHEMAS / "maintenance-conclusion.payload.schema.json"
WARNING_EXAMPLE = EXAMPLES / "warning-raised.json"
CONCLUSION_EXAMPLE = EXAMPLES / "maintenance-conclusion.json"
SHARED_ENUMS = CONTRACTS / "shared-enums.json"

HIGH_SAMPLE = dict(
    temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0
)
# 健康分 100 -> LOW：恢复评估（触发 C-INT-09 自动闭环）
NOMINAL_SAMPLE = dict(
    temperatureC=60.0, vibrationMmS=1.0, currentA=10.0, rotationalSpeedRpm=1500.0
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_errors(schema: dict, instance: object) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(instance)
    ]


def _emit_warning_event(client) -> dict:
    response = client.post(
        EVAL_URL,
        json=health_body(sample=sample_payload(**HIGH_SAMPLE)),
        headers=internal_headers(),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------- 前置：契约文件必须存在且自洽 ----------
def test_contract_files_are_present():
    for path in (
        ENVELOPE_SCHEMA,
        WARNING_PAYLOAD_SCHEMA,
        CONCLUSION_PAYLOAD_SCHEMA,
        WARNING_EXAMPLE,
        CONCLUSION_EXAMPLE,
        SHARED_ENUMS,
    ):
        assert path.is_file(), f"契约文件缺失：{path}"


def test_shipped_warning_example_is_schema_valid():
    """先证明校验器本身可用：契约自带示例必须通过。"""
    example = _load(WARNING_EXAMPLE)
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), example)
    errors += _schema_errors(_load(WARNING_PAYLOAD_SCHEMA), example["payload"])
    assert errors == []


# ---------- 发出的 WarningRaised ----------
def test_emitted_event_passes_envelope_schema(client, captured_events):
    _emit_warning_event(client)
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), captured_events[0])
    assert errors == []


def test_emitted_payload_passes_contract_schema(client, captured_events):
    _emit_warning_event(client)
    errors = _schema_errors(
        _load(WARNING_PAYLOAD_SCHEMA), captured_events[0]["payload"]
    )
    assert errors == []


def test_emitted_event_has_same_keys_as_contract_example(client, captured_events):
    _emit_warning_event(client)
    emitted = captured_events[0]
    example = _load(WARNING_EXAMPLE)

    assert set(emitted) == set(example)
    assert set(emitted["payload"]) == set(example["payload"])
    assert set(emitted["payload"]["metricSnapshot"]) == set(
        example["payload"]["metricSnapshot"]
    )


def test_emitted_identifier_patterns_match_contract(client, captured_events):
    """warningId 与 equipmentId 必须匹配契约里的正则。"""
    import re

    _emit_warning_event(client)
    payload = captured_events[0]["payload"]
    assert re.fullmatch(r"^WARN-[0-9]{8}-[0-9]{4}$", payload["warningId"])
    assert re.fullmatch(r"^EQ-[0-9]{6}$", payload["equipmentId"])


# ---------- 枚举一致性 ----------
def test_warning_status_values_match_shared_enums():
    enums = _load(SHARED_ENUMS)
    assert {status.value for status in WarningStatus} == set(enums["warningStatus"])


def test_risk_level_values_match_shared_enums():
    enums = _load(SHARED_ENUMS)
    assert {level.value for level in RiskLevel} == {
        item["code"] for item in enums["riskLevel"]
    }


def test_contract_example_only_covers_actionable_levels():
    """契约示例里的风险等级必须属于"会触发建单"的等级。"""
    example = _load(WARNING_EXAMPLE)
    assert RiskLevel(example["payload"]["riskLevel"]) in ACTIONABLE_RISK_LEVELS


def test_scoring_output_always_uses_contract_risk_values():
    enums = _load(SHARED_ENUMS)
    allowed = {item["code"] for item in enums["riskLevel"]}

    samples = [
        dict(temperatureC=60.0, vibrationMmS=1.0, currentA=10.0, rotationalSpeedRpm=1500.0),
        dict(temperatureC=78.5, vibrationMmS=6.2, currentA=13.8, rotationalSpeedRpm=1450.0),
        dict(temperatureC=95.0, vibrationMmS=1.0, currentA=1.0, rotationalSpeedRpm=1500.0),
        dict(temperatureC=249.0, vibrationMmS=199.0, currentA=9999.0, rotationalSpeedRpm=100000.0),
    ]
    for sample in samples:
        assert evaluate_sample(sample).risk_level.value in allowed


# ---------- 接收的 MaintenanceConclusionReported ----------
def test_conclusion_example_is_schema_valid():
    """C 会按这个示例发结论；先确认示例本身合法。"""
    example = _load(CONCLUSION_EXAMPLE)
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), example)
    errors += _schema_errors(_load(CONCLUSION_PAYLOAD_SCHEMA), example["payload"])
    assert errors == []


def test_conclusion_example_is_accepted_end_to_end(client, db):
    """把契约示例原样 POST 给 B，必须被接收。"""
    from src.domain import models

    example = _load(CONCLUSION_EXAMPLE)

    response = client.post(
        "/api/v1/integration/maintenance-conclusions",
        json=example,
        headers=internal_headers(),
    )
    # 该示例的 warningId 尚未在本实例中产生 -> 404 是正确行为，
    # 但绝不能是 400（说明我们对契约的理解与 schema 不一致）
    assert response.status_code in (202, 404), response.text
    if response.status_code == 404:
        assert response.json()["code"] == "WARNING_NOT_FOUND"
        assert db.query(models.MaintenanceConclusion).count() == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("eventType", "WarningRaised"),
        ("sourceMember", "MEMBER_B"),
        ("schemaVersion", "1.0"),
    ],
)
def test_conclusion_envelope_constants_are_enforced(client, field, value):
    """包络里的常量字段与契约示例不符时必须 400。"""
    from tests.conftest import conclusion_event

    event = conclusion_event()
    event[field] = value
    response = client.post(
        "/api/v1/integration/maintenance-conclusions",
        json=event,
        headers=internal_headers(),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


# ---------- C-INT-09：预警自动闭环通知 ----------
ENVELOPE_SCHEMA = SCHEMAS / "event-envelope.schema.json"
RESOLVED_PAYLOAD_SCHEMA = SCHEMAS / "warning-resolved.payload.schema.json"
RESOLVED_EXAMPLE = EXAMPLES / "warning-resolved.json"


def _emit_resolution_event(client) -> dict:
    """HIGH 评估建预警并关联工单 → LOW 评估自动闭环 → 返回闭环报文。"""
    _emit_warning_event(client)
    response = client.post(
        EVAL_URL,
        json=health_body(sample=sample_payload(**NOMINAL_SAMPLE)),
        headers=internal_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["warningId"] is None


def test_warning_resolved_contract_files_are_present():
    for path in (RESOLVED_PAYLOAD_SCHEMA, RESOLVED_EXAMPLE):
        assert path.is_file(), f"契约文件缺失：{path}"


def test_shipped_resolved_example_is_schema_valid():
    example = _load(RESOLVED_EXAMPLE)
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), example)
    errors += _schema_errors(_load(RESOLVED_PAYLOAD_SCHEMA), example["payload"])
    assert errors == []


def test_emitted_resolution_passes_envelope_schema(client, captured_resolutions):
    _emit_resolution_event(client)
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), captured_resolutions[0])
    assert errors == []


def test_emitted_resolution_payload_passes_contract_schema(
    client, captured_resolutions
):
    _emit_resolution_event(client)
    errors = _schema_errors(
        _load(RESOLVED_PAYLOAD_SCHEMA), captured_resolutions[0]["payload"]
    )
    assert errors == []


def test_emitted_resolution_has_same_keys_as_contract_example(
    client, captured_resolutions
):
    _emit_resolution_event(client)
    emitted = captured_resolutions[0]
    example = _load(RESOLVED_EXAMPLE)
    assert set(emitted) == set(example)
    assert set(emitted["payload"]) == set(example["payload"])


def test_emitted_resolution_reports_recovery_score(client, captured_resolutions):
    """闭环事件必须回报**恢复**健康分（证明设备已正常），不是预警当初的风险分。"""
    _emit_resolution_event(client)
    payload = captured_resolutions[0]["payload"]
    assert payload["healthScore"] == 100.0
    assert payload["resolvedBy"] == "USER-SYSTEM-AUTO"
    assert payload["linkedOrderId"]


def test_event_types_match_shared_enums():
    """新增事件类型必须登记进 shared-enums 与包络 schema。"""
    from src.domain.enums import OutboxEventType

    enums = _load(SHARED_ENUMS)
    declared = set(enums["eventType"])
    envelope = set(_load(ENVELOPE_SCHEMA)["properties"]["eventType"]["enum"])
    assert OutboxEventType.WARNING_RESOLVED.value == "WarningResolvedReported"
    assert "WarningResolvedReported" in declared
    assert declared == envelope, "shared-enums 与包络 schema 的 eventType 必须一致"


def test_resolved_envelope_constants_are_enforced():
    from src.application.evaluation_service import build_warning_resolved_event
    from src.domain import models

    warning = models.Warning(
        warning_id="WARN-20260917-0001",
        equipment_id="EQ-000001",
        risk_level="HIGH",
        health_score=49.4,
        suspected_fault="主轴轴承振动异常",
        recommended_action="建议停机检查",
        status="RESOLVED",
        warning_at=datetime(2026, 9, 17, 8, 29, 55),
        model_version="rule-engine-1.0.0",
        linked_order_id="WO-20260917-0001",
        version=2,
    )
    event = build_warning_resolved_event(
        warning, 100.0, "trace-test-b-0001", datetime.now()
    )
    errors = _schema_errors(_load(ENVELOPE_SCHEMA), event)
    errors += _schema_errors(_load(RESOLVED_PAYLOAD_SCHEMA), event["payload"])
    assert errors == []
