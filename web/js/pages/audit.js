/* ============================================================================
 * 页面：审计日志（#/audit）
 *
 * 数据来源（真实接口）：
 *   C GET /api/v1/audit-logs  支持 orderId / operatorId / action / from / to
 *
 * 数据模型（apps/maintenance/src/domain/models.py 的 AuditLog）：
 *   action / operatorId / beforeValue / afterValue / detail / traceId / createdAt
 *   —— before→after 是状态迁移，traceId 是跨服务串联键。
 *
 * action 取值（实测 C 库全集 + 生成点）：
 *   COMMAND:<动作>              work_order_service.py:275（唯一命令入口）
 *   AUTO_CREATE_FROM_WARNING    :129   预警自动建单
 *   CREATE_MANUAL               :173   人工报修建单
 *   AUTO_CLOSE_ON_WARNING_RESOLVED :354  设备恢复正常自动结单
 *   AUTO_CLOSE_SKIPPED          :362   已进维修，留人工流程
 * ==========================================================================*/

// 动作分类：用于 KPI 与筛选，取值与 OD_ACTION_ZH 保持一致
const AUDIT_KIND = {
  "COMMAND:CONFIRM":              { k:"command", zh:"确认工单" },
  "COMMAND:ASSIGN":               { k:"command", zh:"派单" },
  "COMMAND:ACCEPT":               { k:"command", zh:"接单" },
  "COMMAND:START":                { k:"command", zh:"开始维修" },
  "COMMAND:WAIT_FOR_PARTS":       { k:"command", zh:"等待备件" },
  "COMMAND:RESUME":               { k:"command", zh:"恢复维修" },
  "COMMAND:SUBMIT_FOR_INSPECTION":{ k:"command", zh:"提交验收" },
  "COMMAND:PASS_INSPECTION":      { k:"command", zh:"验收通过" },
  "COMMAND:REJECT_INSPECTION":    { k:"command", zh:"验收驳回" },
  "COMMAND:CANCEL":               { k:"command", zh:"取消工单" },
  AUTO_CREATE_FROM_WARNING:       { k:"auto", zh:"预警自动建单" },
  CREATE_MANUAL:                  { k:"manual", zh:"人工报修建单" },
  AUTO_CLOSE_ON_WARNING_RESOLVED: { k:"auto", zh:"设备恢复自动结单" },
  AUTO_CLOSE_SKIPPED:             { k:"auto", zh:"设备恢复但留人工流程" },
};
function auditZh(a){ return (AUDIT_KIND[a] || {}).zh || a; }
function auditKind(a){ return (AUDIT_KIND[a] || {}).k || "other"; }

function auditFiltered(){
  const f = state.auditFilter || {};
  let list = state.auditLogs || [];
  if (f.kind) list = list.filter(a => auditKind(a.action) === f.kind);
  if (f.kw) {
    const k = f.kw.toLowerCase();
    list = list.filter(a => [a.orderId, a.action, a.operatorId, a.detail, a.traceId]
      .some(v => String(v || "").toLowerCase().includes(k)));
  }
  return list;
}

function applyAuditFilter(){
  state.auditFilter = {
    kind: (document.getElementById("au-kind") || {}).value || "",
    kw: ((document.getElementById("au-kw") || {}).value || "").trim(),
  };
  return route(true);
}
function resetAuditFilter(){ state.auditFilter = null; return route(true); }

function auditTableHtml(){
  const list = auditFiltered();
  const rows = list.map(a => {
    const k = auditKind(a.action);
    const dot = k === "auto" ? "○" : k === "manual" ? "◐" : "●";
    const tone = k === "auto" ? "var(--purple)" : k === "manual" ? "var(--yellow)" : "var(--cyan)";
    const mig = (a.beforeValue || a.afterValue)
      ? '<span class="mono mini">' + h(a.beforeValue || "—") + '</span>'
        + ' <span style="color:var(--dim2)">→</span> '
        + '<span class="mono mini">' + h(a.afterValue || "—") + '</span>'
      : '<span class="mini" style="color:var(--dim2)">—</span>';
    return [
      '<span class="mini">' + fmtTimeSec(a.createdAt) + '</span>',
      '<span style="color:' + tone + '">' + dot + '</span> <span class="mono mini">'
        + h(a.action) + '</span><div class="mini">' + h(auditZh(a.action)) + '</div>',
      '<span class="mono mini">' + h(a.operatorId || "—") + '</span>',
      '<span class="mono mini">' + h(a.orderId || "—") + '</span>',
      mig,
      '<span class="mini">' + h(a.detail || "—") + '</span>',
      '<span class="mono mini">' + h(a.traceId || "—") + '</span>',
    ];
  });
  return '<div id="audit-tbl">'
    + table(["时间", "动作", "操作人", "工单", "状态迁移", "明细", "traceId"], rows,
        { emptyText: "无匹配的审计记录", emptyHint: "换个筛选条件，或先做几次工单操作产生日志" })
    + '</div>';
}

function auditBody(){
  const all = state.auditLogs || [];
  const list = auditFiltered();
  const f = state.auditFilter || {};

  const nCommand = all.filter(a => auditKind(a.action) === "command").length;
  const nAuto    = all.filter(a => auditKind(a.action) === "auto").length;
  const nManual  = all.filter(a => auditKind(a.action) === "manual").length;
  const nOperators = new Set(all.map(a => a.operatorId).filter(Boolean)).size;
  // 系统操作人：C 侧有两套标识（建单用 "system"、自动结单用 USER-SYSTEM-AUTO）
  const nSystem  = all.filter(a => /system/i.test(a.operatorId || "")).length;

  let html = pageHdr("审计日志", "全链路操作留痕 · traceId 追溯",
    '<div class="btn-group">'
    + '<button class="btn btn-o btn-sm" onclick="exportAuditCsv()">⇩ 导出 CSV</button>'
    + '</div>');

  html += noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/audit-logs</span>"
    + "（支持 <span class=\"mono\">orderId / operatorId / action / from / to</span> 过滤，已实读 "
    + all.length + " 条）。审计表 <span class=\"mono\">AuditLog</span> 记录每个动作的操作人、"
    + "<span class=\"mono\">before→after</span> 状态迁移与 traceId。");

  html += '<div class="grid g5 mt">'
    + kpi("cyan",   "命令操作", nCommand, "人工推进状态机")
    + kpi("purple", "自动操作", nAuto, "预警建单 / 恢复结单")
    + kpi("yellow", "人工报修", nManual, "非预警来源")
    + kpi("green",  "操作人数", nOperators, "含系统账号 " + nSystem + " 次")
    + kpi("dim",    "记录总数", all.length, "全部历史")
    + '</div>';

  html += '<div class="card mt"><div class="toolbar">'
    + '<input id="au-kw" placeholder="工单号 / 动作 / 操作人 / traceId" style="width:250px" value="'
      + h(f.kw || "") + '">'
    + '<select id="au-kind"><option value="">全部动作</option>'
      + [["command","命令操作（人工推进）"],["auto","自动操作（系统触发）"],
         ["manual","人工报修建单"]]
          .map(o => '<option value="' + o[0] + '"' + (f.kind === o[0] ? " selected" : "") + '>'
            + h(o[1]) + '</option>').join("")
    + '</select>'
    + '<button class="btn btn-o btn-sm" onclick="applyAuditFilter()">查询</button>'
    + '<button class="btn btn-o btn-sm" onclick="resetAuditFilter()">重置</button>'
    + '<span class="mini" style="margin-left:auto">显示 ' + list.length + ' / ' + all.length + ' 条</span>'
    + '</div>'
    + auditTableHtml()
    + '</div>';

  // traceId 全链路说明：这是本页最有价值的分析视角
  const traces = {};
  all.forEach(a => {
    if (!a.traceId) return;
    traces[a.traceId] = traces[a.traceId] || new Set();
    traces[a.traceId].add(a.orderId);
  });

  html += '<div class="grid g-2-1 mt">'
    + '<div class="card">' + sect("traceId 全链路追溯", "跨服务串联键")
    + '<div class="mini" style="line-height:1.9">一次 <span class="mono">simulate ABNORMAL</span> '
    + '注入会贯穿四个服务，共用同一个 <span class="mono">traceId</span>：</div>'
    + '<div class="timeline mt">'
    + '<div class="tl ok"><div class="tt">A · 写入遥测并登记状态</div>'
      + '<div class="td"><span class="mono">POST /api/v1/equipment/{id}/simulate</span>'
      + ' → 写入 telemetry 样点，必要时推进设备状态</div></div>'
    + '<div class="tl ok"><div class="tt">B · 评估健康并建预警</div>'
      + '<div class="td"><span class="mono">POST /api/v1/health-evaluations</span>'
      + ' → 落库评估记录；判定 HIGH/CRITICAL 时建预警并 enqueue '
      + '<span class="mono">WarningRaised</span></div></div>'
    + '<div class="tl ok"><div class="tt">C · 接收预警建工单</div>'
      + '<div class="td"><span class="mono">POST /api/v1/integration/warning-events</span>'
      + ' → 建工单 + 写 <span class="mono">AUTO_CREATE_FROM_WARNING</span> 审计</div></div>'
    + '<div class="tl ok"><div class="tt">D · 投递通知</div>'
      + '<div class="td"><span class="mono">POST /api/v1/notifications</span>'
      + '（C-INT-07，<span style="color:var(--yellow)">当前尚无调用点</span>）</div></div>'
    + '</div>'
    + '<div class="mini mt" style="line-height:1.8">'
      + '<b>实测验证：</b>本页 ' + all.length + ' 条审计覆盖 <span class="mono">'
      + Object.keys(traces).length + '</span> 个 traceId。每个 '
      + '<span class="mono">AUTO_CREATE_FROM_WARNING</span> / '
      + '<span class="mono">AUTO_CLOSE_ON_WARNING_RESOLVED</span> 的 traceId，'
      + '都能在 B 服务 <span class="mono">outbox_event</span> 表里找到同名记录'
      + '——B 的事件投递与 C 的审计落库确实共用同一个 traceId，跨服务因果链真实可追。'
      + '<br>注意：traceId 是<b>请求级</b>的，同一工单的多个命令各带各自的 traceId。'
      + '串<b>一次完整流程</b>看<b>工单号</b>，串<b>跨服务的一次调用</b>才看 traceId。</div>'
    + '</div>'

    + '<div class="card">' + sect("审计的三个层次", "已实现与规划")
    + table(["层次", "内容", "状态"], [
        ["业务审计", "工单状态流转写入 audit_log，记录 before/after 与操作人",
         '<span class="pill b-green">已实现</span>'],
        ["安全审计", "登录成功/失败、越权拒绝（服务端返回结构化错误并记日志）",
         '<span class="pill b-yellow">部分实现</span>'],
        ["数据审计", "谁改了设备档案、调整了预警阈值——配置类变更同样需要留痕",
         '<span class="pill b-dim">规划中</span>'],
      ])
    + '<div class="timeline mt">'
    + '<div class="tl ok"><div class="tt">操作人由服务端覆写</div><div class="td">'
      + '命令体里的 <code>operatorId</code> 不可信——服务端从 JWT 取真实身份覆写，'
      + '所以上表的操作人列是可信的。</div></div>'
    + '<div class="tl warn"><div class="tt">系统操作人有两个标识</div><div class="td">'
      + '预警自动建单记 <code>system</code>，设备恢复自动结单记 '
      + '<code>USER-SYSTEM-AUTO</code>（<code>work_order_service.py</code> 的 '
      + '<code>AUTO_OPERATOR_ID</code>）。查"系统做了什么"要同时匹配两者。</div></div>'
    + '<div class="tl warn"><div class="tt">备件动作暂不入审计</div><div class="td">'
      + '备件的批准/发料/退料改的是库存表，<code>spare_service.py</code> 目前没写 '
      + '<code>audit_log</code>——所以本页看不到 SPR-* 记录。这是已知缺口。</div></div>'
    + '</div></div></div>';

  return html;
}

function exportAuditCsv(){
  downloadCsv("audit-logs",
    ["时间", "动作", "中文", "操作人", "工单", "迁移前", "迁移后", "明细", "traceId"],
    auditFiltered().map(a => [a.createdAt, a.action, auditZh(a.action), a.operatorId,
      a.orderId, a.beforeValue || "", a.afterValue || "", a.detail || "", a.traceId || ""]));
}

registerPage("audit", {
  async load(ctx){
    state.auditLogs = await loadAuditLogs();
    return auditBody();
  },
  async poll(ctx){
    if (!document.getElementById("audit-tbl")) return;
    state.auditLogs = await loadAuditLogs();
    const el = document.getElementById("audit-tbl");
    if (el) el.outerHTML = auditTableHtml();
  },
});
