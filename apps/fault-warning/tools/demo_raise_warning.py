#!/usr/bin/env python
"""演示：触发一次 HIGH 风险预警，并把 ``WarningRaised`` 事件送到成员 C。

放在本模块自己的目录下（``apps/fault-warning/tools/``）而不是仓库根目录的
``scripts/``：按 ``.github/CODEOWNERS``，``/scripts/`` 属于成员 D，
B 不应往里添加文件。

用法（在 ``apps/fault-warning`` 目录下执行）::

    # 方式一（推荐）：走完整 C-INT-02 评估链路，B 自己评分并外送事件
    python tools/demo_raise_warning.py evaluate

    # 方式二：只构造一条契约示例报文，直接 POST 到 C 的 C-INT-03
    python tools/demo_raise_warning.py direct

    # 覆盖地址与令牌
    python tools/demo_raise_warning.py evaluate \\
        --member-b http://localhost:8102 \\
        --member-c http://localhost:8103 \\
        --token local-development-internal-token

成员 C 未就绪时脚本**不会抛栈**：它会打印目标 URL、完整报文和失败原因，
方便先检查报文是否符合 ``contracts/examples/warning-raised.json``。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

import httpx

# 契约 examples/warning-raised.json 的样本：评分后恰好落在 HIGH 段
HIGH_SAMPLE = {
    "temperatureC": 78.5,
    "vibrationMmS": 6.2,
    "currentA": 13.8,
    "rotationalSpeedRpm": 1450.0,
}

EQUIPMENT_ID = "EQ-000001"
DEFAULT_MEMBER_B = "http://localhost:8102"
DEFAULT_MEMBER_C = "http://localhost:8103"
DEFAULT_TOKEN = "local-development-internal-token"
TIMEOUT = 10.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _internal_headers(token: str, trace_id: str, idempotency_key: str) -> dict:
    return {
        "X-Internal-Token": token,
        "X-Trace-Id": trace_id,
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }


def _print_response(response: httpx.Response) -> None:
    print(f"HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    except ValueError:
        print(response.text)


def _build_health_evaluation_body() -> dict:
    sample_id = str(uuid.uuid4())
    return {
        "evaluationId": str(uuid.uuid4()),
        "equipmentId": EQUIPMENT_ID,
        "requestedAt": _now(),
        "sample": {"sampleId": sample_id, "measuredAt": _now(), **HIGH_SAMPLE},
    }


def _build_direct_event(warning_id: str, trace_id: str) -> dict:
    """按 contracts/examples/warning-raised.json 的结构手工构造事件。"""
    return {
        "eventId": str(uuid.uuid4()),
        "eventType": "WarningRaised",
        "schemaVersion": "2.0",
        "occurredAt": _now(),
        "sourceMember": "MEMBER_B",
        "traceId": trace_id,
        "payload": {
            "warningId": warning_id,
            "equipmentId": EQUIPMENT_ID,
            "riskLevel": "HIGH",
            "healthScore": 49.4,
            "suspectedFault": "主轴轴承振动异常",
            "recommendedAction": "建议停机检查主轴轴承及润滑状态",
            "warningAt": _now(),
            "modelVersion": "rule-engine-1.0.0",
            "metricSnapshot": {
                "sampleId": str(uuid.uuid4()),
                "measuredAt": _now(),
                **HIGH_SAMPLE,
            },
        },
    }


def run_evaluate(args: argparse.Namespace) -> int:
    """调用 B 自己的 C-INT-02，由 B 完成评分与事件外送。"""
    trace_id = f"trace-demo-{uuid.uuid4().hex[:8]}"
    url = f"{args.member_b.rstrip('/')}/api/v1/health-evaluations"
    body = _build_health_evaluation_body()

    print("=" * 72)
    print("[1/2] 调用成员 B 的健康评估（C-INT-02）")
    print(f"      POST {url}")
    print("      请求体：")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print("-" * 72)

    try:
        response = httpx.post(
            url,
            headers=_internal_headers(args.token, trace_id, str(uuid.uuid4())),
            json=body,
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        print(f"成员 B 不可达：{type(exc).__name__}: {exc}")
        print("请先启动：uvicorn src.main:app --port 8102")
        return 1

    _print_response(response)
    if response.status_code != 200:
        return 1

    data = response.json()
    warning_id = data.get("warningId")
    print("-" * 72)
    print(
        f"      评分结果：healthScore={data['healthScore']} "
        f"riskLevel={data['riskLevel']} warningId={warning_id}"
    )
    print(
        "      只有 HIGH / CRITICAL 才会生成 WarningId 并向 C 外送事件；"
        "LOW / MEDIUM 时 warningId 为 null。"
    )

    if not warning_id:
        print("\n本次评估未达到告警等级，流程结束。")
        return 0

    print()
    print("[2/2] 回查预警，确认 C 是否已建单")
    detail_url = f"{args.member_b.rstrip('/')}/api/v1/warnings/{warning_id}"
    print(f"      GET {detail_url}")
    try:
        detail = httpx.get(
            detail_url,
            headers={"X-User-Id": args.user_id, "X-Trace-Id": trace_id},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        print(f"查询失败：{type(exc).__name__}: {exc}")
        return 1

    _print_response(detail)
    if detail.status_code == 200:
        warning = detail.json()
        if warning.get("linkedOrderId"):
            print(f"\n闭环成立：C 已建立工单 {warning['linkedOrderId']}")
        else:
            print(
                "\n预警已生成，但尚未关联工单。若 C 未启动，事件会留在 outbox "
                "中等待重试（status 仍为 OPEN，linkedOrderId 为 null）。"
            )
    return 0


def run_direct(args: argparse.Namespace) -> int:
    """不经 B，直接把一条 WarningRaised 报文投给 C 的 C-INT-03。"""
    trace_id = f"trace-demo-{uuid.uuid4().hex[:8]}"
    warning_id = f"WARN-{datetime.now(timezone.utc):%Y%m%d}-0001"
    event = _build_direct_event(warning_id, trace_id)
    url = f"{args.member_c.rstrip('/')}/api/v1/integration/warning-events"
    event_id = event["eventId"]

    print("=" * 72)
    print("直接向成员 C 发送 WarningRaised（C-INT-03）")
    print(f"POST {url}")
    print("请求体（结构对齐 contracts/examples/warning-raised.json）：")
    print(json.dumps(event, ensure_ascii=False, indent=2))
    print("-" * 72)

    try:
        response = httpx.post(
            url,
            headers=_internal_headers(args.token, trace_id, event_id),
            json=event,
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        print(f"成员 C 不可达：{type(exc).__name__}: {exc}")
        print("上面就是完整报文；C 就绪后用同样的 Body 重放即可（保持 eventId 不变）。")
        return 1

    _print_response(response)
    if response.status_code == 202:
        print(f"\nC 已接收，自动建单号：{response.json().get('orderId')}")
        print("再次执行同样请求（eventId 相同）会得到 duplicate=true 与同一 orderId。")
        return 0

    print(
        f"\n未收到预期的 202（实际 {response.status_code}）。"
        "若该响应来自本机代理或环境拦截而非成员 C，请检查直连地址与网络配置。"
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="触发一次 HIGH 风险预警并演示 B -> C 的事件外送",
    )
    parser.add_argument(
        "mode",
        choices=["evaluate", "direct"],
        help="evaluate=走 B 的完整评估链路；direct=直接向 C 发送契约报文",
    )
    parser.add_argument("--member-b", default=DEFAULT_MEMBER_B, help="成员 B 直连地址")
    parser.add_argument("--member-c", default=DEFAULT_MEMBER_C, help="成员 C 直连地址")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="X-Internal-Token 取值")
    parser.add_argument("--user-id", default="USER-B-001", help="查询预警时使用的用户")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "evaluate":
        return run_evaluate(args)
    return run_direct(args)


if __name__ == "__main__":
    sys.exit(main())
