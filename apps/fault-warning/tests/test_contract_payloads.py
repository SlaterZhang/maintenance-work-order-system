"""对外报文与 ``contracts/`` 契约的机器可校验一致性。

对应 Wave 2 任务书验收条件：

    "发送的 WarningRaised 报文与 contracts/examples/warning-raised.json
    结构一致，能通过 warning-raised.payload.schema.json 校验"

这些用例直接读取仓库根目录的 ``contracts/``，因此契约一旦漂移会立刻失败，
而不是各模块悄悄维护两套定义。
"""

import json
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
