r"""E2E-01~04 业务闭环全链路演示/回归脚本（Wave 3）。

对真实运行的四个服务完整执行愿景文档第十章演示叙事：
  E2E-01 严重预警自动建单（A 查设备 → B 评估 → B→C 异步建单）
  E2E-02 工单全流程人工处置（D 种子用户按状态机：确认/派单/接单/开始/提交/验收）
  E2E-03 维修结论回流 B（PASS_INSPECTION → C→B，预警被关闭 RESOLVED）
  E2E-04 设备状态恢复（C→A：RUNNING → MAINTAINING → RUNNING）

用法：
  powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1        先启动四服务
  python scripts\e2e_demo.py                                            运行本脚本（全过退出码 0）
  powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -Stop 收尾停止
"""
import argparse
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

EQUIPMENT_ID = "EQ-000001"
DEMO_SAMPLE = {
    "temperatureC": 92.0,
    "vibrationMmS": 8.5,
    "currentA": 18.2,
    "rotationalSpeedRpm": 1450,
}
SUPERVISOR = "USER-D-001"
ENGINEER = "USER-C-002"
POLL_TIMEOUT_SECONDS = 15.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


def new_trace_id() -> str:
    return f"trace-e2e-{uuid.uuid4().hex[:16]}"


class E2E:
    def __init__(self, args):
        self.args = args
        self.client = httpx.Client(timeout=10.0)
        self.checks_total = 0
        self.checks_failed = 0
        self.start = time.monotonic()
        self.last_request = None

    def url(self, member: str, path: str) -> str:
        return f"{getattr(self.args, 'base_' + member)}{path}"

    def internal_headers(self, trace_id: str, idem: str | None = None) -> dict:
        headers = {
            "X-Internal-Token": self.args.token,
            "X-Trace-Id": trace_id,
        }
        if idem:
            headers["Idempotency-Key"] = idem
        return headers

    def request(self, method: str, url: str, *, headers=None, json=None) -> httpx.Response:
        self.last_request = {
            "method": method, "url": url,
            "headers": dict(headers or {}), "json": json,
        }
        return self.client.request(method, url, headers=headers, json=json)

    def step(self, tag: str, summary: str, status) -> None:
        print(f"[{tag}] {summary}"
              + (f" -> HTTP {status}" if status is not None else ""))

    def check(self, tag: str, cond: bool, ok_msg: str, fail_msg: str) -> bool:
        self.checks_total += 1
        if cond:
            print(f"    √ {ok_msg}")
            return True
        self.checks_failed += 1
        print(f"    × {fail_msg}")
        req = self.last_request or {}
        print("  失败请求全文：")
        print(f"    {req.get('method')} {req.get('url')}")
        print(f"    headers={req.get('headers')}")
        print(f"    body={req.get('json')}")
        print(f"  断言失败，中止（步骤 {tag}）。")
        sys.exit(1)

    def done(self) -> int:
        elapsed = time.monotonic() - self.start
        print()
        print("==================== 四场景总结 ====================")
        for line in self.summary:
            print(line)
        print(f"总断言：{self.checks_total - self.checks_failed} 通过 / "
              f"{self.checks_failed} 失败，总耗时 {elapsed:.2f}s")
        return 0 if self.checks_failed == 0 else 1


def get_equipment(ctx: E2E) -> dict:
    r = ctx.request("GET", ctx.url("a", f"/api/v1/equipment/{EQUIPMENT_ID}"))
    if r.status_code != 200:
        ctx.check("equip", False, "", f"查询设备失败 HTTP {r.status_code}: {r.text}")
    return r.json()


def evaluate(ctx: E2E, evaluation_id: str, trace_id: str) -> dict:
    body = {
        "evaluationId": evaluation_id,
        "equipmentId": EQUIPMENT_ID,
        "requestedAt": now_iso(),
        "sample": {"sampleId": str(uuid.uuid4()), "measuredAt": now_iso(),
                   **DEMO_SAMPLE},
    }
    r = ctx.request(
        "POST", ctx.url("b", "/api/v1/health-evaluations"),
        headers=ctx.internal_headers(trace_id, evaluation_id), json=body)
    if r.status_code != 200:
        ctx.check("eval", False, "", f"健康评估失败 HTTP {r.status_code}: {r.text}")
    return r.json()


def work_order_command(ctx: E2E, order_id: str, action: str, operator: str,
                       expected_version: int, extra: dict | None = None) -> dict:
    body = {"action": action, "operatorId": operator,
            "expectedVersion": expected_version}
    if extra:
        body.update(extra)
    r = ctx.request(
        "POST", ctx.url("c", f"/api/v1/work-orders/{order_id}/commands"),
        headers={
            "X-User-Id": operator,
            "X-Trace-Id": new_trace_id(),
            "Idempotency-Key": str(uuid.uuid4()),
        }, json=body)
    if r.status_code != 200:
        ctx.check("cmd", False, "",
                  f"{action} 失败 HTTP {r.status_code}: {r.text}")
    return r.json()


def poll_work_order(ctx: E2E, warning_id: str, trace_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        r = ctx.request(
            "GET", ctx.url("c", f"/api/v1/work-orders?warningId={warning_id}"),
            headers={"X-User-Id": ENGINEER, "X-Trace-Id": trace_id})
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                return items[0]
        time.sleep(1.0)
    ctx.check("poll", False, "",
              f"{POLL_TIMEOUT_SECONDS}s 内未查到 warningId={warning_id} 对应的自动建单工单")
    raise SystemExit(1)


def run(ctx: E2E) -> None:
    ctx.summary = []
    trace = new_trace_id()

    print("========== E2E-01 严重预警自动建单（文档第十章叙事） ==========")
    ctx.step("E2E-01/1", f"GET A /api/v1/equipment/{EQUIPMENT_ID} 记录初始状态", None)
    equipment0 = get_equipment(ctx)
    ctx.check("E2E-01/1", equipment0["currentStatus"] == "RUNNING",
              f"设备初始状态 RUNNING（version={equipment0['version']}）",
              f"设备初始状态非 RUNNING：{equipment0['currentStatus']}")
    initial_status = equipment0["currentStatus"]
    initial_version = equipment0["version"]

    ctx.step("E2E-01/2",
             "POST B /api/v1/health-evaluations（92℃/8.5mm·s⁻¹/18.2A/1450rpm 文档演示值）", None)
    evaluation_id = str(uuid.uuid4())
    result = evaluate(ctx, evaluation_id, trace)
    ctx.check("E2E-01/3", result["riskLevel"] == "CRITICAL",
              f"风险等级 CRITICAL（healthScore={result['healthScore']}，"
              f"suspectedFault={result['suspectedFault']}）",
              f"风险等级非 CRITICAL：{result}")
    ctx.check("E2E-01/3", result["healthScore"] < 40,
              f"健康度 {result['healthScore']} < 40（设备变红）",
              f"健康度未低于 40：{result['healthScore']}")
    warning_id = result["warningId"]
    ctx.check("E2E-01/3", bool(warning_id),
              f"产生严重预警 warningId={warning_id}", f"未产生预警：{result}")

    ctx.step("E2E-01/4",
             f"轮询 C /api/v1/work-orders?warningId={warning_id}（B 异步发 WarningRaised 建单）", None)
    order = poll_work_order(ctx, warning_id, trace)
    ctx.check("E2E-01/5", order["status"] == "PENDING_CONFIRMATION",
              f"自动建单 {order['orderId']}，status={order['status']}",
              f"工单状态非 PENDING_CONFIRMATION：{order['status']}")
    ctx.check("E2E-01/5", order["equipmentId"] == EQUIPMENT_ID,
              f"工单设备 equipmentId={order['equipmentId']}",
              f"工单设备不符：{order['equipmentId']}")
    order_id = order["orderId"]
    ctx.summary.append(f"E2E-01 严重预警自动建单 ......... PASS（{warning_id} → {order_id}）")

    print()
    print("========== E2E-02 工单全流程人工处置（文档第五章状态机） ==========")
    version = order["version"]
    flow = [
        ("CONFIRM", SUPERVISOR, None, "PENDING_ASSIGNMENT", "确认"),
        ("ASSIGN", SUPERVISOR, {"assigneeId": ENGINEER}, "PENDING_ACCEPTANCE", "派单"),
        ("ACCEPT", ENGINEER, None, "PENDING_MAINTENANCE", "接单"),
        ("START", ENGINEER, None, "MAINTAINING", "开始维修"),
    ]
    for action, operator, extra, expect_status, label in flow:
        ctx.step("E2E-02", f"{action}（{label}，操作人 {operator}，expectedVersion={version}）", None)
        resp = work_order_command(ctx, order_id, action, operator, version, extra)
        version = resp["version"]
        ctx.check("E2E-02", resp["status"] == expect_status,
                  f"{label}成功，工单状态 {resp['status']}，version={version}",
                  f"{action} 后状态应为 {expect_status}，实际 {resp['status']}")
        if action == "START":
            ctx.step("E2E-04/2", "GET A 设备详情（C 主动通知 A，设备应进入 MAINTAINING）", None)
            eq_m = get_equipment(ctx)
            ctx.check("E2E-04/2", eq_m["currentStatus"] == "MAINTAINING",
                      f"START 后设备 currentStatus={eq_m['currentStatus']}（version={eq_m['version']}）",
                      f"START 后设备状态应 MAINTAINING，实际 {eq_m['currentStatus']}")
            maintaining_status = eq_m["currentStatus"]

    ctx.step("E2E-02", "SPARE_REQUEST 备件流程（可选）", None)
    print("    - 跳过：C 服务无备件种子数据且未提供备件创建 API（任务书标注可选）")

    conclusion = {
        "rootCause": "主轴轴承润滑不足导致振动升高",
        "measures": "补充润滑并更换磨损轴承，完成空载和带载试运行",
        "result": "RECOVERED",
        "effective": True,
        "completedAt": now_iso(),
        "downtimeMinutes": 168,
    }
    ctx.step("E2E-02",
             f"SUBMIT_FOR_INSPECTION（提交验收，conclusion.completedAt 为 ISO 时间字符串）", None)
    resp = work_order_command(ctx, order_id, "SUBMIT_FOR_INSPECTION", ENGINEER,
                              version, {"conclusion": conclusion})
    version = resp["version"]
    ctx.check("E2E-02", resp["status"] == "PENDING_INSPECTION",
              f"提交验收成功，工单状态 PENDING_INSPECTION（HTTP 200 未再触发 DateTime 列 500）",
              f"提交验收后状态应 PENDING_INSPECTION，实际 {resp['status']}")
    ctx.check("E2E-02", resp["conclusion"]["rootCause"] == conclusion["rootCause"],
              "维修结论已记录（rootCause/measures/result/effective/completedAt）",
              f"维修结论缺失：{resp.get('conclusion')}")

    ctx.step("E2E-02", f"PASS_INSPECTION（验收通过，操作人 {SUPERVISOR}）", None)
    resp = work_order_command(ctx, order_id, "PASS_INSPECTION", SUPERVISOR, version)
    ctx.check("E2E-02", resp["status"] == "COMPLETED",
              f"验收通过，工单状态 COMPLETED（version={resp['version']}）",
              f"验收后状态应 COMPLETED，实际 {resp['status']}")

    ctx.step("E2E-04/3", "GET A 设备详情（验收通过，设备应恢复 RUNNING）", None)
    eq_f = get_equipment(ctx)
    ctx.check("E2E-04/3", eq_f["currentStatus"] == "RUNNING",
              f"验收后设备 currentStatus={eq_f['currentStatus']}（version={eq_f['version']}）",
              f"验收后设备状态应 RUNNING，实际 {eq_f['currentStatus']}")
    final_status = eq_f["currentStatus"]
    ctx.summary.append(f"E2E-02 工单全流程人工处置 ....... PASS（{order_id} 已 COMPLETED）")

    print()
    print("========== E2E-03 维修结论回流 B（C-INT-05，预警应被关闭） ==========")
    ctx.step("E2E-03/1", f"GET B /api/v1/warnings/{warning_id}（契约预警详情路径）", None)
    r = ctx.request("GET", ctx.url("b", f"/api/v1/warnings/{warning_id}"),
                    headers=ctx.internal_headers(new_trace_id()))
    resolved = None
    if r.status_code == 200:
        resolved = r.json().get("status")
        ctx.check("E2E-03/1", resolved in ("RESOLVED", "CLOSED", "已处理"),
                  f"B 侧预警状态 {resolved}", f"B 侧预警状态异常：{r.json()}")
    else:
        print(f"    ! 成员B 未实现契约的 GET /api/v1/warnings/{{warningId}}"
              f"（HTTP {r.status_code}），改用探测性再评估断言：")
        print("      B 评估逻辑对 HIGH/CRITICAL 会复用该设备 OPEN/ACKNOWLEDGED 的既有预警；")
        print("      若新评估返回新 warningId，即证明原预警已被 C 的维修结论置为 RESOLVED。")
        ctx.step("E2E-03/2", "POST B /api/v1/health-evaluations 探测性再评估（同演示异常值）", None)
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        probe_warning_id = warning_id
        while time.monotonic() < deadline:
            probe = evaluate(ctx, str(uuid.uuid4()), new_trace_id())
            probe_warning_id = probe.get("warningId")
            if probe_warning_id and probe_warning_id != warning_id:
                break
            time.sleep(2.0)
        ctx.check("E2E-03/2",
                  bool(probe_warning_id) and probe_warning_id != warning_id,
                  f"再评估返回新预警 {probe_warning_id}（≠ {warning_id}）⇒ 原预警已被维修结论关闭 RESOLVED",
                  f"{POLL_TIMEOUT_SECONDS}s 内原预警 {warning_id} 仍处于打开状态，结论回流失败")
        print(f"    （探测性再评估产生的新预警 {probe_warning_id} 为系统持续监测的正常行为，")
        print("      其触发的自动建单留在 PENDING_CONFIRMATION，不影响本闭环）")
    ctx.summary.append(
        f"E2E-03 维修结论回流 B ......... PASS（{warning_id} → 已关闭 RESOLVED）")

    print()
    print("========== E2E-04 设备状态恢复（C-INT-04，轨迹断言） ==========")
    ctx.step("E2E-04/1", f"GET A /api/v1/equipment/{EQUIPMENT_ID} 确认最终状态", None)
    eq_end = get_equipment(ctx)
    ctx.check("E2E-04/1", initial_status == "RUNNING",
              f"轨迹起点：工单开始前 RUNNING（version={initial_version}）",
              f"轨迹起点异常：{initial_status}")
    ctx.check("E2E-04/2", maintaining_status == "MAINTAINING",
              "轨迹中点：START 后 MAINTAINING（C 主动通知 A）",
              f"轨迹中点异常：{maintaining_status}")
    ctx.check("E2E-04/3", final_status == "RUNNING" and eq_end["currentStatus"] == "RUNNING",
              f"轨迹终点：验收通过后 RUNNING（version={eq_end['version']}，全程递增）",
              f"轨迹终点异常：{final_status} / {eq_end['currentStatus']}")
    ctx.check("E2E-04/3",
              initial_version < eq_end["version"],
              f"设备 version {initial_version} → {eq_end['version']}（状态变更留痕）",
              "设备 version 未变化")
    print(f"    设备状态变化轨迹：RUNNING → MAINTAINING → RUNNING √")
    ctx.summary.append(
        f"E2E-04 设备状态恢复 ......... PASS（RUNNING → MAINTAINING → RUNNING）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E 业务闭环演示：严重预警自动建单 → 工单全流程处置 → 结论回流 B → 设备状态恢复")
    parser.add_argument("--base-a", default="http://127.0.0.1:8101",
                        help="成员A 设备监测服务地址")
    parser.add_argument("--base-b", default="http://127.0.0.1:8102",
                        help="成员B 故障预警服务地址")
    parser.add_argument("--base-c", default="http://127.0.0.1:8103",
                        help="成员C 维修工单服务地址")
    parser.add_argument("--base-d", default="http://127.0.0.1:8104",
                        help="成员D 身份通知服务地址")
    parser.add_argument("--token", default="dev-internal-token-change-me",
                        help="内部接口令牌 X-Internal-Token")
    args = parser.parse_args()

    ctx = E2E(args)
    try:
        run(ctx)
    finally:
        ctx.client.close()
    return ctx.done()


if __name__ == "__main__":
    sys.exit(main())
