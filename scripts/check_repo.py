#!/usr/bin/env python3
"""Validate repository structure, OpenAPI, shared enums and event examples."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover - friendly setup error
    print("缺少校验依赖，请执行：python -m pip install -r requirements-dev.txt")
    print(f"原始错误：{exc}")
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README-TEAM.md",
    "CONTRIBUTING.md",
    ".editorconfig",
    ".gitattributes",
    ".github/pull_request_template.md",
    ".github/CODEOWNERS.template",
    ".github/workflows/team-quality-gate.yml",
    "contracts/openapi.yaml",
    "contracts/shared-enums.json",
    "contracts/schemas/event-envelope.schema.json",
    "contracts/schemas/warning-raised.payload.schema.json",
    "contracts/schemas/equipment-status-changed.payload.schema.json",
    "contracts/schemas/maintenance-conclusion.payload.schema.json",
    "contracts/examples/warning-raised.json",
    "contracts/examples/equipment-status-changed.json",
    "contracts/examples/maintenance-conclusion.json",
    "apps/integration-quality/README.md",
]

EVENTS = {
    "WarningRaised": {
        "file": "warning-raised.json",
        "schema": "warning-raised.payload.schema.json",
        "source": "MEMBER_B",
    },
    "EquipmentStatusChanged": {
        "file": "equipment-status-changed.json",
        "schema": "equipment-status-changed.payload.schema.json",
        "source": "MEMBER_C",
    },
    "MaintenanceConclusionReported": {
        "file": "maintenance-conclusion.json",
        "schema": "maintenance-conclusion.payload.schema.json",
        "source": "MEMBER_C",
    },
}


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.ok: list[str] = []

    def require(self, condition: bool, success: str, failure: str) -> None:
        if condition:
            self.ok.append(success)
        else:
            self.errors.append(failure)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_structure(result: Result, strict: bool) -> None:
    missing = [item for item in REQUIRED_PATHS if not (ROOT / item).is_file()]
    result.require(not missing, "必需文件齐全", f"缺少必需文件：{', '.join(missing)}")

    codeowners = ROOT / ".github" / "CODEOWNERS"
    if not codeowners.exists():
        message = "尚未生成 .github/CODEOWNERS；运行 scripts/configure_team.py"
        (result.errors if strict else result.warnings).append(message)
    else:
        content = codeowners.read_text(encoding="utf-8")
        has_placeholder = "__MEMBER_" in content
        result.require(not has_placeholder, "CODEOWNERS 已配置", "CODEOWNERS 仍包含占位符")

    forbidden = [
        ROOT / ".env",
        ROOT / "id_rsa",
        ROOT / "id_ed25519",
    ]
    present = [path.name for path in forbidden if path.exists()]
    result.require(not present, "未发现常见秘密文件", f"发现不得提交的文件：{present}")


def validate_openapi(result: Result) -> None:
    path = ROOT / "contracts" / "openapi.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"OpenAPI YAML 无法解析：{exc}")
        return

    result.require(
        isinstance(document, dict) and str(document.get("openapi", "")).startswith("3.1"),
        "OpenAPI 版本为 3.1",
        "OpenAPI 顶层版本缺失或不是 3.1",
    )
    paths = document.get("paths", {}) if isinstance(document, dict) else {}
    result.require(len(paths) == 6, "六个跨模块 REST 路径齐全", f"预期 6 个路径，实际 {len(paths)} 个")

    operation_ids: list[str] = []
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if isinstance(operation, dict) and operation.get("operationId"):
                operation_ids.append(operation["operationId"])
    result.require(
        len(operation_ids) == len(set(operation_ids)) == 6,
        "OpenAPI operationId 唯一",
        "OpenAPI operationId 缺失或重复",
    )


def schema_errors(schema: dict[str, Any], instance: Any) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    formatted: list[str] = []
    for error in errors:
        location = ".".join(str(part) for part in error.path) or "<root>"
        formatted.append(f"{location}: {error.message}")
    return formatted


def validate_contracts(result: Result) -> None:
    contract_dir = ROOT / "contracts"
    try:
        enums = load_json(contract_dir / "shared-enums.json")
        envelope_schema = load_json(contract_dir / "schemas" / "event-envelope.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"公共契约 JSON 无法解析：{exc}")
        return

    result.require(
        re.fullmatch(r"\d+\.\d+\.\d+", str(enums.get("contractVersion", ""))) is not None,
        "公共枚举版本格式正确",
        "contractVersion 必须使用语义版本，例如 1.0.0",
    )

    enum_event_types = set(enums.get("eventType", []))
    result.require(
        enum_event_types == set(EVENTS),
        "事件类型与公共枚举一致",
        f"事件类型不一致：枚举={sorted(enum_event_types)}，预期={sorted(EVENTS)}",
    )

    enum_sources = set(enums.get("sourceMember", []))
    schema_sources = set(envelope_schema["properties"]["sourceMember"]["enum"])
    expected_sources = {"MEMBER_A", "MEMBER_B", "MEMBER_C", "MEMBER_D"}
    result.require(
        enum_sources == schema_sources == expected_sources,
        "四名成员来源枚举一致",
        "sourceMember 必须在公共枚举与事件包络中同时包含 MEMBER_A 至 MEMBER_D",
    )

    event_ids: set[str] = set()
    for event_type, config in EVENTS.items():
        example_path = contract_dir / "examples" / config["file"]
        schema_path = contract_dir / "schemas" / config["schema"]
        try:
            example = load_json(example_path)
            payload_schema = load_json(schema_path)
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{event_type} 文件无法解析：{exc}")
            continue

        errors = schema_errors(envelope_schema, example)
        errors.extend(schema_errors(payload_schema, example.get("payload")))
        if example.get("eventType") != event_type:
            errors.append(f"eventType 应为 {event_type}")
        if example.get("sourceMember") != config["source"]:
            errors.append(f"sourceMember 应为 {config['source']}")
        event_id = example.get("eventId")
        if event_id in event_ids:
            errors.append(f"eventId 重复：{event_id}")
        event_ids.add(event_id)

        if errors:
            result.errors.append(f"{config['file']} 校验失败：" + "；".join(errors))
        else:
            result.ok.append(f"{config['file']} 契约通过")

    schema_risk = set(
        load_json(contract_dir / "schemas" / "warning-raised.payload.schema.json")
        ["properties"]["riskLevel"]["enum"]
    )
    enum_risk = {item["code"] for item in enums.get("riskLevel", [])}
    result.require(schema_risk == enum_risk, "风险等级在枚举与 Schema 中一致", "风险等级定义不一致")

    schema_status = set(
        load_json(contract_dir / "schemas" / "equipment-status-changed.payload.schema.json")
        ["properties"]["targetStatus"]["enum"]
    )
    enum_status = set(enums.get("equipmentStatus", []))
    result.require(schema_status == enum_status, "设备状态在枚举与 Schema 中一致", "设备状态定义不一致")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验四人协作仓库")
    parser.add_argument("--strict", action="store_true", help="将未配置项视为错误，供 CI 使用")
    args = parser.parse_args()

    result = Result()
    validate_structure(result, args.strict)
    validate_openapi(result)
    validate_contracts(result)

    for message in result.ok:
        print(f"[OK] {message}")
    for message in result.warnings:
        print(f"[WARN] {message}")
    for message in result.errors:
        print(f"[ERROR] {message}")

    if result.errors:
        print(f"校验失败：{len(result.errors)} 个错误，{len(result.warnings)} 个警告")
        return 1

    print(f"校验通过：{len(result.ok)} 项，{len(result.warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
