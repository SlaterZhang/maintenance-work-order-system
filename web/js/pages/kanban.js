/* ============================================================================
 * 页面：工单看板 Kanban（#/kanban）
 * 数据来源：C GET /api/v1/work-orders（state.orders，由 data.js 载入）
 * 布局类名来自 web/css/platform.css:208-219 的 .kanban / .kcol / .kcard 家族，
 * 不另造样式——原型 web/prototype/platform.html:1180 用的就是这一套。
 * ==========================================================================*/

// 看板七列：只列「流转中」的状态。COMPLETED / CANCELLED 是终态，单列出来没有
// 流转意义，改由顶部 KPI 表达。
const KANBAN_COLS = [
  { s:"PENDING_CONFIRMATION", c:"var(--yellow)" },
  { s:"PENDING_ASSIGNMENT",   c:"var(--orange)" },
  { s:"PENDING_ACCEPTANCE",   c:"var(--cyan)" },
  { s:"PENDING_MAINTENANCE",  c:"var(--purple)" },
  { s:"MAINTAINING",          c:"var(--red)" },
  { s:"WAITING_PARTS",        c:"var(--dim)" },
  { s:"PENDING_INSPECTION",   c:"var(--green)" },
];

function kanbanOrderCard(o){
  const eq = (state.equipment || []).find(e => e.equipmentId === o.equipmentId) || {};
  const pri = (o.priority || "P3").toLowerCase();     // p1..p4 → .kcard.p1
  const overdue = o.dueAt && new Date(o.dueAt) < new Date()
    && !["COMPLETED", "CANCELLED"].includes(o.status);
  return '<div class="kcard ' + pri + '" onclick="openOrderFromKanban(\'' + h(o.orderId) + '\')">'
    + '<div class="kt">' + h(o.title || "—") + '</div>'
    + '<div class="km"><span class="mono">' + h(o.orderId) + '</span>'
      + tag("workOrderPriority", o.priority) + '</div>'
    + '<div class="km"><span class="mono">' + h(o.equipmentId || "—") + '</span>'
      + '<span>' + h(eq.name || o.equipmentNameSnapshot || "") + '</span></div>'
    + '<div class="km">'
      + '<span>👤 ' + h(o.assigneeId || "未派单") + '</span>'
      + '<span' + (overdue ? ' style="color:var(--red)"' : "") + '>⏱ '
        + (o.dueAt ? fmtTime(o.dueAt).slice(5, 16) : "—") + '</span>'
      + '<span>v' + h(o.version) + '</span></div>'
    + '</div>';
}

function openOrderFromKanban(orderId){ navigate("#/order/" + orderId); }

function applyKanbanFilter(){
  const kw = (document.getElementById("kb-kw") || {}).value || "";
  const pri = (document.getElementById("kb-pri") || {}).value || "";
  const asg = (document.getElementById("kb-asg") || {}).value || "";
  state.kanbanFilter = { kw:kw.trim(), pri, asg };
  return route(true);
}

function resetKanbanFilter(){
  state.kanbanFilter = null;
  return route(true);
}

function kanbanBody(){
  const f = state.kanbanFilter || {};
  let list = state.orders || [];
  if (f.kw) {
    const k = f.kw.toLowerCase();
    list = list.filter(o => [o.orderId, o.title, o.equipmentId, o.equipmentNameSnapshot]
      .some(v => String(v || "").toLowerCase().includes(k)));
  }
  if (f.pri) list = list.filter(o => o.priority === f.pri);
  if (f.asg) list = list.filter(o => (o.assigneeId || "") === f.asg);

  const openAll = (state.orders || []).filter(o => !["COMPLETED", "CANCELLED"].includes(o.status));
  const prios = [...new Set((state.orders || []).map(o => o.priority).filter(Boolean))].sort();
  const asgs = [...new Set((state.orders || []).map(o => o.assigneeId).filter(Boolean))].sort();

  let html = pageHdr("工单看板", "按状态列看板视图 · 点击卡片进详情",
    '<div class="btn-group">'
    + '<button class="btn btn-o btn-sm" onclick="exportKanbanCsv()">⇩ 导出 CSV</button>'
    + '<button class="btn btn-p btn-sm" onclick="openCreateOrderModal()">＋ 新建工单</button>'
    + '</div>');

  html += noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/work-orders</span>（已实现）。"
    + "列顺序即服务端状态机顺序；卡片点击进工单详情，动作按钮按当前状态与权限动态渲染。");

  const byS = s => openAll.filter(o => o.status === s).length;
  const totalOpen = openAll.length;
  const overdueN = openAll.filter(o => o.dueAt && new Date(o.dueAt) < new Date()).length;
  const p1n = openAll.filter(o => o.priority === "P1").length;
  html += '<div class="grid g5 mt">'
    + kpi("cyan",  "未结工单", totalOpen, "含流转中全部状态")
    + kpi("red",   "P1 紧急",  p1n, "SLA 12h")
    + kpi("yellow", "已超期",  overdueN, overdueN ? "需立即处理" : "全部在期内")
    + kpi("purple", "待检验",  byS("PENDING_INSPECTION"), "质检确认效果")
    + kpi("green", "已完成",   (state.orders || []).filter(o => o.status === "COMPLETED").length, "全部历史")
    + '</div>';

  html += '<div class="card mt"><div class="toolbar">'
    + '<input id="kb-kw" placeholder="工单号 / 标题 / 设备" value="' + h(f.kw || "") + '" style="width:220px">'
    + '<select id="kb-pri"><option value="">全部优先级</option>'
      + prios.map(p => '<option value="' + h(p) + '"' + (f.pri === p ? " selected" : "") + '>'
          + h(enumZh("workOrderPriority", p, p)) + '</option>').join("")
    + '</select>'
    + '<select id="kb-asg"><option value="">全部负责人</option>'
      + asgs.map(a => '<option value="' + h(a) + '"' + (f.asg === a ? " selected" : "") + '>'
          + h(a) + '</option>').join("")
    + '</select>'
    + '<button class="btn btn-o btn-sm" onclick="applyKanbanFilter()">查询</button>'
    + '<button class="btn btn-o btn-sm" onclick="resetKanbanFilter()">重置</button>'
    + '<span class="mini" style="margin-left:auto">显示 ' + KANBAN_COLS.length + ' 个流转态 · 共 '
      + totalOpen + ' 张未结工单</span>'
    + '</div>';

  // platform.css 的 .kanban 写死 repeat(6,…)（原型是 6 列）；本页列数不同，
  // 用内联样式覆盖，否则多出的列会被挤到第二行。
  html += '<div class="kanban" style="grid-template-columns:repeat('
    + KANBAN_COLS.length + ',minmax(158px,1fr))">';
  KANBAN_COLS.forEach(col => {
    const items = list.filter(o => o.status === col.s);
    html += '<div class="kcol">'
      + '<div class="kh"><span class="dot" style="background:' + col.c + '"></span>'
        + h(enumZh("workOrderStatus", col.s, col.s))
        + '<span class="n">' + items.length + '</span></div>'
      + '<div style="margin-top:9px;display:flex;flex-direction:column;gap:8px">'
      + (items.length ? items.map(kanbanOrderCard).join("")
          : '<div class="empty" style="padding:16px 6px"><span class="ei">◌</span>暂无工单</div>')
      + '</div></div>';
  });
  html += '</div></div>';

  // 状态机与流转规则说明（口径来自 apps/maintenance/src/domain/state_machine.py）
  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("工单状态机", "9 态 / 10 动作")
    + table(["状态", "含义", "可执行动作", "权限码"], [
        ["PENDING_CONFIRMATION", "待确认", "CONFIRM / CANCEL", "WORK_ORDER_CONFIRM"],
        ["PENDING_ASSIGNMENT", "待派单", "ASSIGN / CANCEL", "WORK_ORDER_ASSIGN"],
        ["PENDING_ACCEPTANCE", "待接单", "ACCEPT / ASSIGN（改派）/ CANCEL", "WORK_ORDER_ACCEPT"],
        ["PENDING_MAINTENANCE", "待维修", "START", "WORK_ORDER_MAINTAIN"],
        ["MAINTAINING", "维修中", "WAIT_FOR_PARTS / SUBMIT_FOR_INSPECTION", "WORK_ORDER_MAINTAIN"],
        ["WAITING_PARTS", "待备件", "RESUME", "WORK_ORDER_MAINTAIN"],
        ["PENDING_INSPECTION", "待检验", "PASS_INSPECTION / REJECT_INSPECTION", "WORK_ORDER_INSPECT"],
        ["COMPLETED", "已完成", "—（终态）", "—"],
        ["CANCELLED", "已取消", "—（终态）", "—"],
      ].map(r => ['<span class="mono mini">' + r[0] + '</span>'
                     + '<br>' + tag("workOrderStatus", r[0]), '<span class="mini">' + r[1] + '</span>',
                   '<span class="mini mono">' + r[2] + '</span>',
                   '<span class="mini mono">' + r[3] + '</span>']))
    + '</div>'
    + '<div class="card">' + sect("流转规则要点", "服务端强校验")
    + '<div class="timeline">'
    + '<div class="tl ok"><div class="tt">取消仅限早三态</div><div class="td">'
      + '<code>CANCEL</code> 只允许 <code>PENDING_CONFIRMATION / PENDING_ASSIGNMENT / '
      + 'PENDING_ACCEPTANCE</code>。一旦进入维修（MAINTAINING / WAITING_PARTS / '
      + 'PENDING_INSPECTION）就不允许取消——这会掩盖已发生的维修成本。</div></div>'
    + '<div class="tl ok"><div class="tt">完成必须带结论</div><div class="td">'
      + '<code>SUBMIT_FOR_INSPECTION</code> 必须携带 <code>completedAt</code> 以及 '
      + '<code>rootCause / measures / effective</code>，这些字段同时是回写 B 服务的维修结论内容。</div></div>'
    + '<div class="tl ok"><div class="tt">操作人由服务端覆写</div><div class="td">'
      + '命令体里的操作人字段不可信——服务端从 JWT 取真实身份覆写，审计日志记录 '
      + '<code>before_value / after_value / traceId</code>。</div></div>'
    + '<div class="tl warn"><div class="tt">验收通过后的副作用</div><div class="td">'
      + '若工单标记 <code>restoreEquipment</code>，则通知 A 服务把设备状态复位为 '
      + '<code>RUNNING</code>；同时向 B 服务发送维修结论。</div></div>'
    + '</div></div></div>';

  return html;
}

function exportKanbanCsv(){
  const cols = KANBAN_COLS.map(c => c.s);
  const rows = (state.orders || []).filter(o => cols.includes(o.status))
    .map(o => [o.orderId, enumZh("workOrderStatus", o.status, o.status), o.priority,
               o.equipmentId, o.title, o.assigneeId || "", o.sourceType || "",
               o.createdAt, o.dueAt || "", o.version]);
  downloadCsv("work-orders-kanban", ["工单号", "状态", "优先级", "设备", "标题", "负责人",
    "来源", "创建时间", "截止时间", "版本"], rows);
}

registerPage("kanban", {
  async load(ctx){
    if (!state.orders.length) await loadOrders();
    return kanbanBody();
  },
  async poll(ctx){
    // 看板只做整体重渲染，不做局部替换：卡片自带 onclick 与数量徽标，
    // 局部替换容易与筛选输入框的状态打架。
    if (!document.getElementById("kb-kw")) return;
    await loadOrders();
    if (state.kanbanFilter) return;   // 有筛选条件时不动 DOM，避免打断输入
    await refreshCurrent();
  },
});
