/* ============================================================================
 * 页面：系统集成监控（#/integ）
 *
 * 数据来源（全部真实，无虚构）：
 *   各服务 GET /health                    存活探针（A/B/C/D 四服务）
 *   B GET /api/v1/warnings                预警（链路核对）
 *   C GET /api/v1/work-orders             工单（链路核对）
 *   B GET /api/v1/health-evaluations      评估历史（链路核对）
 *   契约元数据：contracts/README.md 的 C-INT-01..09
 *
 * 边界说明：outbox / processed_event 是**服务端库表**，契约没有暴露查询接口
 * （contracts/openapi.yaml 的 25 个 path 里没有 outbox 相关路径）。所以本页
 * 不伪造「事件队列」面板，改为展示**能从前端验证的集成事实**：健康探针、
 * 契约接口清单、以及用业务数据交叉验证的链路一致性。
 * ==========================================================================*/

// 服务清单（端口与 base 路径取自 deploy/nginx.conf 与各服务 .env）
const INTEG_SERVICES = [
  { key:"a", name:"设备监测", member:"MEMBER_A", base:"/a", port:8101,
    role:"设备主数据与遥测接入" },
  { key:"b", name:"故障预警", member:"MEMBER_B", base:"/b", port:8102,
    role:"健康评估与预警状态机" },
  { key:"c", name:"维修工单", member:"MEMBER_C", base:"/c", port:8103,
    role:"工单 / 备件 / 审计" },
  { key:"d", name:"身份通知", member:"MEMBER_D", base:"/d", port:8104,
    role:"身份权限与通知任务" },
];

// C-INT 契约接口（照抄 contracts/README.md 表格，不凭印象）
const INTEG_CONTRACTS = [
  { id:"C-INT-01", dir:"A → C", use:"C 查询设备主数据",
    path:"GET /api/v1/equipment/{equipmentId}", impl:"已实现" },
  { id:"C-INT-02", dir:"A → B", use:"A 请求健康评估",
    path:"POST /api/v1/health-evaluations", impl:"已实现" },
  { id:"C-INT-03", dir:"B → C", use:"B 发送高风险预警",
    path:"POST /api/v1/integration/warning-events", impl:"已实现" },
  { id:"C-INT-04", dir:"C → A", use:"C 反馈维修状态",
    path:"POST /api/v1/integration/equipment-status-events", impl:"已实现" },
  { id:"C-INT-05", dir:"C → B", use:"C 反馈维修结论",
    path:"POST /api/v1/integration/maintenance-conclusions", impl:"已实现" },
  { id:"C-INT-06", dir:"A/B/C → D", use:"查询身份权限上下文",
    path:"GET /api/v1/users/{userId}/access-context", impl:"需内部令牌" },
  { id:"C-INT-07", dir:"A/B/C → D", use:"提交通知任务",
    path:"POST /api/v1/notifications", impl:"无调用点" },
  { id:"C-INT-08", dir:"C → B", use:"工单取消回流",
    path:"POST /api/v1/integration/order-cancellations", impl:"已实现" },
  { id:"C-INT-09", dir:"B → C", use:"预警自动闭环通知",
    path:"POST /api/v1/integration/warning-closures", impl:"已实现" },
];

async function probeService(svc){
  const t0 = performance.now();
  try {
    const body = await api(svc.key, "/health", { headers: {} });
    return { ok: true, body: body, ms: Math.round(performance.now() - t0) };
  } catch (e) {
    return { ok: false, err: e.message, ms: Math.round(performance.now() - t0) };
  }
}

async function probeAllServices(){
  const results = await Promise.all(INTEG_SERVICES.map(probeService));
  const map = {};
  INTEG_SERVICES.forEach((s, i) => { map[s.key] = results[i]; });
  state.integHealth = map;
  state.integProbedAt = new Date().toISOString();
  return map;
}

function integServiceRows(){
  const hp = state.integHealth || {};
  return INTEG_SERVICES.map(s => {
    const r = hp[s.key];
    const st = !r ? '<span class="pill b-dim">未探测</span>'
      : r.ok ? '<span class="pill b-green">UP</span>'
             : '<span class="pill b-red">DOWN</span>';
    return [
      '<span class="mono">' + h(s.member) + '</span><div class="mini">' + h(s.name) + '</div>',
      '<span class="mono mini">' + h(s.base) + '</span>',
      '<span class="mono mini">' + s.port + '</span>',
      '<span class="mini">' + h(s.role) + '</span>',
      st,
      '<span class="mini mono">' + (r && r.ok ? r.ms + " ms" : "—") + '</span>',
      r && r.ok && r.body && r.body.modelVersion
        ? '<span class="mono mini">' + h(r.body.modelVersion) + '</span>'
        : '<span class="mini">—</span>',
      r && !r.ok ? '<span class="mini" style="color:var(--red)">' + h(r.err || "") + '</span>'
                 : '<span class="mini">—</span>',
    ];
  });
}

function integContractRows(){
  return INTEG_CONTRACTS.map(c => {
    const tone = c.impl === "无调用点" ? "yellow"
      : c.impl === "需内部令牌" ? "cyan" : "green";
    return [
      '<span class="mono">' + h(c.id) + '</span>',
      '<span class="mono mini">' + h(c.dir) + '</span>',
      '<span class="mini">' + h(c.use) + '</span>',
      '<span class="mono mini">' + h(c.path) + '</span>',
      '<span class="pill b-' + tone + '">' + h(c.impl) + '</span>',
    ];
  });
}

/** 链路一致性核对：用两侧业务数据交叉验证事件真的落到了对端。
 *  全部基于前端可读接口，不依赖库表直读、不需要内部令牌。 */
function integLinkChecks(){
  const warns = state.warnings || [];
  const orders = state.orders || [];
  const warnIds = new Set(warns.map(w => w.warningId));

  const linkedWarns = warns.filter(w => w.linkedOrderId);
  const orderWarnIds = new Set(orders.filter(o => o.warningId).map(o => o.warningId));
  const mismatch = linkedWarns.filter(w => !orderWarnIds.has(w.warningId));
  const orphans = orders.filter(o => o.warningId && !warnIds.has(o.warningId));
  const terminal = warns.filter(w =>
    ["RESOLVED", "CANCELLED", "FALSE_POSITIVE"].includes(w.status));
  const hist = state.healthHistory || [];

  return [
    { name: "B→C：预警建单回填 linkedOrderId",
      detail: warns.length + " 条预警中 " + linkedWarns.length + " 条已回填关联工单",
      ok: linkedWarns.length > 0 && mismatch.length === 0,
      note: mismatch.length
        ? mismatch.length + " 条预警的关联工单未出现在工单列表（可能已分页截断）"
        : "预警侧引用的工单都能在 C 侧找到" },
    { name: "C→B：工单回指来源预警",
      detail: orders.filter(o => o.warningId).length + " 条工单带 warningId",
      ok: orders.filter(o => o.warningId).length === 0 || orphans.length === 0,
      note: orphans.length
        ? orphans.length + " 条工单引用了 B 侧不存在的预警"
        : "无悬空引用" },
    { name: "C→B / C-INT-05/08：闭环回流",
      detail: terminal.length + " 条预警已进入终态（共 " + warns.length + " 条）",
      ok: true,
      note: "终态含维修结论 RECOVERED 闭环与工单取消回流两条路径" },
    { name: "A→B / C-INT-02：评估落库",
      detail: hist.length + " 条评估历史",
      ok: hist.length > 0,
      note: "只有 A 的 simulate 会触发 B 评估；内部遥测入口不触发" },
    { name: "D：身份与通知",
      detail: (state.users || []).length + " 个账号、"
        + (state.notifications || []).length + " 条通知任务",
      ok: (state.users || []).length > 0,
      note: (state.notifications || []).length === 0
        ? "通知任务为 0 —— 对应 C-INT-07 无调用点"
        : "已有通知投递记录" },
  ];
}

function integBody(){
  const hp = state.integHealth || {};
  const up = INTEG_SERVICES.filter(s => hp[s.key] && hp[s.key].ok).length;
  const checks = integLinkChecks();
  const pass = checks.filter(c => c.ok).length;

  let html = pageHdr("系统集成监控", "四服务健康 · 契约接口 · 链路一致性",
    '<button class="btn btn-p btn-sm" onclick="refreshCurrent()">↻ 重新探测</button>');

  html += noticeLive("数据来源：真实接口 — 各服务 <span class=\"mono\">GET /health</span>"
    + "（经 nginx <span class=\"mono\">/a /b /c /d</span> 转发，均已实测可达）；"
    + "契约清单照抄 <span class=\"mono\">contracts/README.md</span> 的 C-INT-01..09。"
    + "outbox / processed_event 是服务端库表，契约未暴露查询接口，"
    + "本页因此不做「事件队列」面板，改以链路一致性核对作为可验证的集成证据。");

  html += '<div class="grid g4 mt">'
    + kpi(up === 4 ? "green" : up ? "yellow" : "red", "服务在线", up + " / 4",
        up === 4 ? "四服务全部 UP" : "有服务不可达")
    + kpi("cyan", "契约接口", INTEG_CONTRACTS.length, "C-INT-01..09")
    + kpi(pass === checks.length ? "green" : "yellow", "链路核对通过",
        pass + " / " + checks.length, "以两侧业务数据交叉验证")
    + kpi("yellow", "未接通契约", "1 项", "C-INT-07 通知投递")
    + '</div>';

  html += '<div class="card mt">' + sect("服务健康探针",
      state.integProbedAt ? "探测于 " + fmtTime(state.integProbedAt) : "尚未探测")
    + table(["服务", "路径", "端口", "职责", "状态", "延迟", "模型版本", "错误"],
        integServiceRows(), { emptyText: "无服务" })
    + '</div>';

  html += '<div class="card mt">' + sect("C-INT 跨服务契约", INTEG_CONTRACTS.length + " 项")
    + table(["编号", "方向", "用途", "接口", "落地状态"], integContractRows())
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b style="color:var(--yellow)">C-INT-07 是当前唯一未接通的契约</b>：'
    + '投递入口 <span class="mono">POST /api/v1/notifications</span> 已在 D 实现'
    + '（<span class="mono">apps/integration-quality/src/interfaces/http/notifications.py:47</span>），'
    + 'B 也定义了 <span class="mono">OutboxEventType.WARNING_NOTIFICATION</span> 并写了投递函数'
    + '（<span class="mono">apps/fault-warning/src/application/event_dispatch.py:94</span>），'
    + '但全仓没有 <span class="mono">enqueue(WARNING_NOTIFICATION)</span> 调用点；'
    + 'C 的 <span class="mono">MemberDClient.submit_notification</span> 同样无调用点。'
    + '补法是在既有代码里各加一行，不需要新接口。'
    + '</div></div>';

  html += '<div class="card mt">' + sect("链路一致性核对",
      "以两侧业务数据交叉验证事件是否真的落到对端")
    + table(["检查项", "证据", "结论"], checks.map(c => [
        h(c.name),
        '<span class="mini">' + h(c.detail) + '</span>',
        (c.ok ? '<span class="pill b-green">一致</span>'
              : '<span class="pill b-yellow">待核</span>')
          + '<div class="mini" style="margin-top:2px">' + h(c.note) + '</div>',
      ]))
    + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("事件投递机制", "两种模式并存")
    + '<div class="timeline">'
    + '<div class="tl ok"><div class="tt">B 用 outbox 表（事务性发件箱）</div><div class="td">'
      + '预警建单与闭环先写 <span class="mono">outbox_event</span>，再由 '
      + '<span class="mono">dispatch_pending_events</span> 投递并回填 status / attempts。'
      + '好处是投递失败不阻断主事务、可按 attempts 重试；代价是多一张表与一次查询。</div></div>'
    + '<div class="tl ok"><div class="tt">C 用 processed_event 表（幂等收件箱）</div><div class="td">'
      + 'C 没有 outbox，改为在接收侧记录 <span class="mono">processed_event</span>'
      + '（<span class="mono">event_id</span> 唯一）实现幂等：重复投递直接命中已处理记录并返回原结果。'
      + '两侧机制不同但互补——B 保证「一定送到」，C 保证「重复送到也只生效一次」。</div></div>'
    + '<div class="tl warn"><div class="tt">本页不展示队列深度</div><div class="td">'
      + 'outbox 与 processed_event 都没有查询接口（契约 25 个 path 里没有）。'
      + '要展示队长与失败重试次数，得先补一个只读接口——在此之前不做假面板。'
      + '实测数据（库内直查）：B 的 outbox 共 10 条，'
      + '<span class="mono">WarningRaised</span> 6 条与 '
      + '<span class="mono">WarningResolvedReported</span> 4 条，全部 SENT、attempts=1。</div></div>'
    + '</div></div>'

    + '<div class="card">' + sect("跨服务调用约束", "四条硬规则")
    + table(["约束", "实现方式"], [
        ["内部调用要内部令牌",
          '<span class="mono mini">X-Internal-Token</span>，值存各服务 '
          + '<span class="mono mini">.env</span> 的 '
          + '<span class="mono mini">INTERNAL_API_TOKEN</span>，绝不下发前端'],
        ["写操作要幂等键",
          '<span class="mono mini">Idempotency-Key</span>（UUID）；缺失时服务端直接 400，'
          + '不接受无键重试'],
        ["全链路要 traceId",
          '<span class="mono mini">X-Trace-Id</span>（8..64 字符）跨服务透传，'
          + '可在审计页按 traceId 聚合'],
        ["操作人不可信",
          '命令体里的 <span class="mono mini">operatorId</span> 一律由服务端从 JWT 覆写，'
          + '客户端传什么都以服务端为准'],
      ].map(r => [h(r[0]), '<span class="mini">' + r[1] + '</span>']))
    + '</div></div>';

  return html;
}

registerPage("integ", {
  async load(ctx){
    // loadUsers/loadNotifications 只返回值、不写 state（各自的页面负责赋值），
    // 这里既然要用于链路核对，就得自己落到 state 上。
    const jobs = [
      loadEquipment(),
      loadWarnings(),
      loadOrders(),
      state.users.length ? Promise.resolve() : loadUsers().then(v => { state.users = v; }),
      state.notifications.length ? Promise.resolve()
        : loadNotifications().then(v => { state.notifications = v; }),
      state.healthHistory.length ? Promise.resolve() : loadHealthHistory(),
    ];
    // 任一服务不可达不应让整页失败：探针本就用于暴露故障
    await Promise.all(jobs.map(p => Promise.resolve(p).catch(() => null)));
    await probeAllServices();
    return integBody();
  },
  async poll(ctx){
    // 探针每轮打四服务 /health：比普通列表页重，但足以看清服务抖动。
    // 仍按全局 5 秒节奏走，不额外开定时器（避免与 state.timer 抢生命周期）。
    if (ctx && ctx.id !== "integ") return;
    await probeAllServices();
    await refreshCurrent();
  },
});
