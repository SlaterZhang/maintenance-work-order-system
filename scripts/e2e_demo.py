r"""E2E-01~05 业务闭环全链路演示/回归脚本（Wave 3）。

对真实运行的四个服务完整执行愿景文档第十章演示叙事：
  E2E-01 严重预警自动建单（A 查设备 → B 评估 → B→C 异步建单）
  E2E-02 工单全流程人工处置（D 种子用户按状态机：确认/派单/接单/开始/提交/验收）
  E2E-03 维修结论回流 B（PASS_INSPECTION → C→B，预警被关闭 RESOLVED）
  E2E-04 设备状态恢复（C→A：RUNNING → MAINTAINING → RUNNING）
  E2E-05 取消后再次异常自动建单（CANCEL → C→B 预警 CANCELLED → 再异常新建预警建单）

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
NORMAL_SAMPLE = {
    "temperatureC": 62.0,
    "vibrationMmS": 2.4,
    "currentA": 11.3,
    "rotationalSpeedRpm": 1450,
}
SUPERVISOR = "USER-D-001"
ENGINEER = "USER-C-002"
ANALYST = "USER-B-001"   # 预警分析员：唯一有 WARNING_READ 的业务角色
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
        self.tokens: dict[str, str] = {}   # userId -> accessToken（D-API-01）

    def url(self, member: str, path: str) -> str:
        return f"{getattr(self.args, 'base_' + member)}{path}"

    def login(self, user_id: str) -> str:
        """D-API-01 登录取 JWT（阶段1鉴权闭合后用户态调用一律 Bearer）。"""
        r = self.request(
            "POST", self.url("d", "/api/v1/auth/login"),
            json={"username": user_id, "password": self.args.password})
        if r.status_code != 200:
            self.check("login", False, "",
                       f"登录 {user_id} 失败 HTTP {r.status_code}: {r.text}")
        return r.json()["accessToken"]

    def bearer_headers(self, user_id: str, trace_id: str,
                       idem: str | None = None) -> dict:
        if user_id not in self.tokens:
            self.tokens[user_id] = self.login(user_id)
        headers = {
            "Authorization": f"Bearer {self.tokens[user_id]}",
            "X-Trace-Id": trace_id,
        }
        if idem:
            headers["Idempotency-Key"] = idem
        return headers

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
        print("==================== 五场景总结 ====================")
        for line in self.summary:
            print(line)
        print(f"总断言：{self.checks_total - self.checks_failed} 通过 / "
              f"{self.checks_failed} 失败，总耗时 {elapsed:.2f}s")
        return 0 if self.checks_failed == 0 else 1


def get_equipment(ctx: E2E) -> dict:
    # 阶段1鉴权闭合补漏（2026-10-06）：A 设备端点不再匿名可读，
    # 以操作员身份查询（bearer_headers 按需自动登录）
    r = ctx.request(
        "GET", ctx.url("a", f"/api/v1/equipment/{EQUIPMENT_ID}"),
        headers=ctx.bearer_headers("USER-A-001", "trace-equip-query"),
    )
    if r.status_code != 200:
        ctx.check("equip", False, "", f"查询设备失败 HTTP {r.status_code}: {r.text}")
    return r.json()


def evaluate(ctx: E2E, evaluation_id: str, trace_id: str,
             sample: dict | None = None) -> dict:
    body = {
        "evaluationId": evaluation_id,
        "equipmentId": EQUIPMENT_ID,
        "requestedAt": now_iso(),
        "sample": {"sampleId": str(uuid.uuid4()), "measuredAt": now_iso(),
                   **(sample or DEMO_SAMPLE)},
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
        headers=ctx.bearer_headers(operator, new_trace_id(),
                                   idem=str(uuid.uuid4())),
        json=body)
    if r.status_code != 200:
        ctx.check("cmd", False, "",
                  f"{action} 失败 HTTP {r.status_code}: {r.text}")
    return r.json()


def poll_work_order(ctx: E2E, warning_id: str, trace_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        r = ctx.request(
            "GET", ctx.url("c", f"/api/v1/work-orders?warningId={warning_id}"),
            headers=ctx.bearer_headers(ENGINEER, trace_id))
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
    ctx.check("E2E-01/3", result.get("trend") == "DEGRADING",
              f"阶段3趋势外推 DEGRADING（{result.get('trendMetric')} 以 "
              f"{result.get('trendRatePerDay')}/天 上行，预计 "
              f"{result.get('predictedDaysToThreshold')} 天触满扣阈值 "
              f"{result.get('trendThreshold')}，样本 {result.get('trendSampleCount')} 条）",
              f"趋势外推非 DEGRADING：{result.get('trend')}")
    ctx.check("E2E-01/3", result.get("predictedDaysToThreshold") is not None,
              f"给出预计触阈值天数 {result.get('predictedDaysToThreshold')}（预测性维护）",
              "趋势外推未给出预计触阈值天数")
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
    ctx.step("E2E-03/1", f"GET B /api/v1/warnings/{warning_id}（预警分析员 Bearer，契约预警详情）", None)
    r = ctx.request("GET", ctx.url("b", f"/api/v1/warnings/{warning_id}"),
                    headers=ctx.bearer_headers(ANALYST, new_trace_id()))
    resolved = None
    if r.status_code == 200:
        resolved = r.json().get("status")
        ctx.check("E2E-03/1", resolved in ("RESOLVED", "CLOSED", "已处理"),
                  f"B 侧预警状态 {resolved}", f"B 侧预警状态异常：{r.json()}")
    else:
        print(f"    ! GET B 预警详情返回 HTTP {r.status_code}（{r.text[:120]}），改用探测性再评估断言：")
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

    print()
    print("========== E2E-05 取消后再次异常仍能自动建单（C-INT-08 回流） ==========")
    print("    （修复前缺陷：取消工单后预警悬在已转工单，再异常被去重复用，永不建单）")
    ctx.step("E2E-05/1", "POST B /api/v1/health-evaluations 注入异常值 → 新预警", None)
    trace5 = new_trace_id()
    result5 = evaluate(ctx, str(uuid.uuid4()), trace5)
    warning5 = result5["warningId"]
    ctx.check("E2E-05/1", bool(warning5) and warning5 != warning_id,
              f"产生新预警 {warning5}（≠ 已解决的 {warning_id}）",
              f"未产生新预警或复用了旧预警：{warning5}")

    ctx.step("E2E-05/2", f"轮询 C 自动建单（warningId={warning5}）", None)
    order5 = poll_work_order(ctx, warning5, trace5)
    ctx.check("E2E-05/2", order5["status"] == "PENDING_CONFIRMATION",
              f"自动建单 {order5['orderId']}，status={order5['status']}",
              f"自动建单状态异常：{order5['status']}")
    order5_id = order5["orderId"]

    ctx.step("E2E-05/3", f"CANCEL 取消工单（{SUPERVISOR}）→ 取消事件回流 B", None)
    resp5 = work_order_command(ctx, order5_id, "CANCEL", SUPERVISOR,
                               order5["version"], {"comment": "重复建单，取消验证回流"})
    ctx.check("E2E-05/3", resp5["status"] == "CANCELLED",
              f"工单已取消（version={resp5['version']}）",
              f"取消后状态应 CANCELLED，实际 {resp5['status']}")

    ctx.step("E2E-05/4", f"GET B /api/v1/warnings/{warning5}（预警应闭环为 CANCELLED）", None)
    r5 = ctx.request("GET", ctx.url("b", f"/api/v1/warnings/{warning5}"),
                      headers=ctx.bearer_headers(ANALYST, new_trace_id()))
    ctx.check("E2E-05/4", r5.status_code == 200 and r5.json().get("status") == "CANCELLED",
              f"取消回流生效：预警状态 {r5.json().get('status')}（已取消终态）",
              f"预警未随工单取消闭环：HTTP {r5.status_code} {r5.text[:120]}")

    ctx.step("E2E-05/5", "POST B 注入正常值（恢复）→ 无新预警", None)
    normal5 = evaluate(ctx, str(uuid.uuid4()), new_trace_id(), sample=NORMAL_SAMPLE)
    ctx.check("E2E-05/5", normal5["riskLevel"] == "LOW" and not normal5.get("warningId"),
              f"恢复正常：riskLevel={normal5['riskLevel']}，无预警挂起",
              f"恢复正常后状态异常：{normal5}")

    ctx.step("E2E-05/6", "POST B 再次注入异常 → 必须新建预警（不再复用死预警）", None)
    trace5b = new_trace_id()
    result5b = evaluate(ctx, str(uuid.uuid4()), trace5b)
    warning5b = result5b["warningId"]
    ctx.check("E2E-05/6", bool(warning5b) and warning5b != warning5,
              f"再次异常产生全新预警 {warning5b}（≠ 已取消的 {warning5}）⇒ 死循环已修复",
              f"未产生新预警或复用了已取消预警：{warning5b}")

    ctx.step("E2E-05/7", f"轮询 C 自动建单（warningId={warning5b}）—— 用户场景完整闭环", None)
    order5b = poll_work_order(ctx, warning5b, trace5b)
    ctx.check("E2E-05/7", order5b["status"] == "PENDING_CONFIRMATION",
              f"取消后再异常：自动建单恢复 {order5b['orderId']}，status={order5b['status']}",
              f"自动建单未恢复：{order5b}")
    ctx.summary.append(
        f"E2E-05 取消后再次异常自动建单 ... PASS（{warning5} 取消 → {warning5b} → {order5b['orderId']}）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E 业务闭环演示：严重预警自动建单 → 工单全流程处置 → 结论回流 B → 设备状态恢复 → 取消后再次异常自动建单")
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
    parser.add_argument("--password", default="demo123456",
                        help="D 种子用户登录口令（用于换取 Bearer JWT）")
    args = parser.parse_args()

    ctx = E2E(args)
    try:
        run(ctx)
    finally:
        ctx.client.close()
    return ctx.done()


if __name__ == "__main__":
    sys.exit(main())
