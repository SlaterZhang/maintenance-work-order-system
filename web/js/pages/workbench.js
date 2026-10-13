/* ==========================================================================
   workbench.js —— A · 角色化工作台（今日待办）
   --------------------------------------------------------------------------
   登录后默认落地页。把「这个角色今天该干什么」按真实数据聚合成待办：

     · 每个角色一个视角区块，只显示登录用户拥有的角色（roleCodes）；
     · 待办全部从实时数据推导（工单/预警/备件申请/备件台账），
       count=0 的项不渲染、整个角色无待办就如实写「今日无待办」；
     · 排序是**规则排序**（优先级 × 状态时效），每项都写明为什么排这里，
       不冒充 AI 预测——本页不做任何打分/预测，只做聚合与排序；
     · 每项可点，跳到对应页面直接处置。

   诚实边界：本页不预测、不打分；"最高优先级"来自工单 priority 字段，
   "已等待"来自 createdAt 与当前时间的差值。
   ========================================================================== */
"use strict";

/* 全部 7 个角色（shared-enums roleCode 的展示顺序） */
const WB_ROLES = [
  ["SYSTEM_ADMIN", "系统管理员"],
  ["MAINTENANCE_SUPERVISOR", "维修主管"],
  ["MAINTENANCE_ENGINEER", "维修工程师"],
  ["WARNING_ANALYST", "预警分析员"],
  ["WAREHOUSE_MANAGER", "库管员"],
  ["INSPECTOR", "检验员"],
  ["EQUIPMENT_OPERATOR", "设备操作员"],
];

function wbRoleZh(code){
  const r = WB_ROLES.find(x => x[0] === code);
  return r ? r[1] : code;
}

function wbPr(p){ return { P1: 0, P2: 1, P3: 2, P4: 3 }[p] != null ? { P1: 0, P2: 1, P3: 2, P4: 3 }[p] : 9; }
function wbRisk(w){
  const m = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  return m[w.riskLevel] != null ? m[w.riskLevel] : 9;
}

/** 已等待时长（createdAt → now），人话格式 */
function wbAge(createdAt){
  if (!createdAt) return "";
  const ms = Date.now() - new Date(createdAt).getTime();
  if (isNaN(ms) || ms < 0) return "";
  const m = Math.floor(ms / 60000);
  if (m < 60) return m + " 分钟";
  const hr = Math.floor(m / 60);
  if (hr < 24) return hr + " 小时";
  return Math.floor(hr / 24) + " 天";
}

/** 待办行 */
function wbItem(t){
  return '<div class="li" style="gap:10px;padding:10px 12px;cursor:pointer" onclick="' + t.jump + '">'
    + '<div style="flex:1">'
      + '<div><b>' + h(t.title) + '</b>'
      + (t.count != null ? '　<span class="pill b-' + t.tone + '">' + h(t.count) + '</span>' : '')
      + '</div>'
      + '<div class="mini" style="margin-top:2px">' + t.why + '</div>'
    + '</div>'
    + '<span class="mini" style="white-space:nowrap">查看 →</span>'
    + '</div>';
}

/**
 * 每个角色的待办视图。d = { orders, warns, parts, reqs }（全部实时数据）。
 * 返回待办数组；空数组 = 该角色今日无待办。
 */
function wbRoleTodos(role, d){
  const orders = d.orders, warns = d.warns, parts = d.parts, reqs = d.reqs;
  const me = (state.user && state.user.userId) || "";
  const items = [];
  const byPr = (a, b) => wbPr(a.priority) - wbPr(b.priority)
    || String(b.createdAt || "").localeCompare(String(a.createdAt || ""));

  if (role === "MAINTENANCE_SUPERVISOR") {
    const conf = orders.filter(o => o.status === "PENDING_CONFIRMATION").sort(byPr);
    if (conf.length) items.push({ title: "待确认工单", count: conf.length, tone: "warn",
      why: conf.slice(0, 3).map(o => h(o.orderId) + "（" + h(o.priority) + " · 已等待 " + wbAge(o.createdAt) + "）").join("、")
        + " —— 按优先级排序，确认后进入派单",
      jump: "navigate('orders')" });
    const asg = orders.filter(o => o.status === "PENDING_ASSIGNMENT").sort(byPr);
    if (asg.length) items.push({ title: "待派单工单", count: asg.length, tone: "warn",
      why: asg.slice(0, 3).map(o => h(o.orderId) + "（" + h(o.priority) + "）").join("、") + " —— 需指派维修工程师",
      jump: "navigate('orders')" });
    const hot = orders.filter(o => ["MAINTAINING", "WAITING_PARTS"].includes(o.status) && ["P1", "P2"].includes(o.priority)).sort(byPr);
    if (hot.length) items.push({ title: "进行中的高优先级维修", count: hot.length, tone: "bad",
      why: hot.slice(0, 3).map(o => h(o.orderId) + "（" + tag("workOrderStatus", o.status) + "）").join("、"),
      jump: "navigate('orders')" });
  }

  if (role === "MAINTENANCE_ENGINEER") {
    const mine = orders.filter(o => o.assigneeId === me && !["COMPLETED", "CANCELLED"].includes(o.status)).sort(byPr);
    if (mine.length) items.push({ title: "分给我的工单", count: mine.length, tone: "warn",
      why: mine.slice(0, 3).map(o => h(o.orderId) + "（" + tag("workOrderStatus", o.status) + "）").join("、"),
      jump: "navigate('orders')" });
    const wait = orders.filter(o => o.status === "PENDING_ACCEPTANCE");
    if (wait.length) items.push({ title: "待接受工单", count: wait.length, tone: "warn",
      why: wait.map(o => h(o.orderId) + "（已等待 " + wbAge(o.createdAt) + "）").join("、"),
      jump: "navigate('orders')" });
    const parts_ = orders.filter(o => o.status === "WAITING_PARTS");
    if (parts_.length) items.push({ title: "等待备件的维修", count: parts_.length, tone: "dim",
      why: parts_.map(o => h(o.orderId)).join("、") + " —— 备件到位后可复工",
      jump: "navigate('orders')" });
  }

  if (role === "WARNING_ANALYST") {
    const open = warns.filter(w => w.status === "OPEN").sort(wbRisk);
    if (open.length) items.push({ title: "待确认预警", count: open.length, tone: "bad",
      why: open.slice(0, 3).map(w => h(w.warningId) + "（" + tag("riskLevel", w.riskLevel) + "）").join("、") + " —— 按风险等级排序",
      jump: "navigate('warns')" });
    const ack = warns.filter(w => w.status === "ACKNOWLEDGED");
    if (ack.length) items.push({ title: "已确认未转工单", count: ack.length, tone: "warn",
      why: ack.slice(0, 3).map(w => h(w.warningId)).join("、") + " —— 确认后决定是否转单",
      jump: "navigate('warns')" });
    const linked = warns.filter(w => w.status === "LINKED_TO_ORDER");
    if (linked.length) items.push({ title: "已转单待闭环", count: linked.length, tone: "dim",
      why: linked.slice(0, 3).map(w => h(w.warningId) + " → " + h(w.linkedOrderId || "—")).join("、"),
      jump: "navigate('warns')" });
  }

  if (role === "WAREHOUSE_MANAGER") {
    const appr = reqs.filter(r => r.status === "PENDING_APPROVAL");
    if (appr.length) items.push({ title: "待审批领用申请", count: appr.length, tone: "warn",
      why: appr.slice(0, 3).map(r => h(r.requestId)).join("、") + " —— 审批后进入备料",
      jump: "navigate('sreq')" });
    const ready = reqs.filter(r => r.status === "APPROVED");
    if (ready.length) items.push({ title: "待发料申请", count: ready.length, tone: "warn",
      why: ready.slice(0, 3).map(r => h(r.requestId)).join("、") + " —— 已审批，待发料",
      jump: "navigate('sreq')" });
    const low = parts.filter(p => Number(p.availableQuantity) < Number(p.reorderPoint));
    if (low.length) items.push({ title: "低于再订货点的备件", count: low.length, tone: "bad",
      why: low.slice(0, 3).map(p => h(p.name) + "（库存 " + h(p.availableQuantity) + " / 再订点 " + h(p.reorderPoint) + "）").join("、"),
      jump: "navigate('spares')" });
  }

  if (role === "INSPECTOR") {
    const insp = orders.filter(o => o.status === "PENDING_INSPECTION");
    if (insp.length) items.push({ title: "待检验工单", count: insp.length, tone: "warn",
      why: insp.slice(0, 3).map(o => h(o.orderId) + "（已等待 " + wbAge(o.createdAt) + "）").join("、"),
      jump: "navigate('orders')" });
  }

  if (role === "EQUIPMENT_OPERATOR") {
    const bad = warns.filter(w => !["RESOLVED", "CANCELLED", "FALSE_POSITIVE"].includes(w.status));
    const eqIds = [...new Set(bad.map(w => w.equipmentId))];
    if (eqIds.length) items.push({ title: "有未闭环预警的设备", count: eqIds.length, tone: "bad",
      why: eqIds.slice(0, 3).map(id => h(id)).join("、") + " —— 关注运行状态",
      jump: "navigate('assets')" });
    const maint = orders.filter(o => ["MAINTAINING", "WAITING_PARTS"].includes(o.status));
    if (maint.length) items.push({ title: "停机/维修中的工单", count: maint.length, tone: "warn",
      why: maint.slice(0, 3).map(o => h(o.orderId) + "（" + tag("workOrderStatus", o.status) + "）").join("、"),
      jump: "navigate('orders')" });
  }

  if (role === "SYSTEM_ADMIN") {
    const openWarns = warns.filter(w => ["OPEN", "ACKNOWLEDGED", "LINKED_TO_ORDER"].includes(w.status));
    const pendConf = orders.filter(o => o.status === "PENDING_CONFIRMATION");
    items.push({ title: "全厂待确认工单", count: pendConf.length, tone: pendConf.length ? "warn" : "ok",
      why: pendConf.length ? "维修主管视角处理" : "各角色待办均已清零",
      jump: "navigate('orders')" });
    items.push({ title: "未闭环预警", count: openWarns.length, tone: openWarns.length ? "warn" : "ok",
      why: openWarns.length ? "含待确认 / 已确认 / 已转单" : "全部预警已闭环",
      jump: "navigate('warns')" });
    items.push({ title: "服务健康检查", tone: "dim",
      why: "A/B/C/D 四服务连通性与延迟",
      jump: "navigate('integ')" });
    items.push({ title: "审计日志", tone: "dim",
      why: "操作留痕与 traceId 追溯",
      jump: "navigate('audit')" });
  }

  return items;
}

/* ---------- 数据装配 ---------- */
async function wbLoadData(){
  await loadCore();
  const errs = {};
  const parts = await api("c", "/api/v1/spare-parts?pageSize=100", { headers: authHeaders() })
    .catch(e => { errs.parts = e.message; return { items: [] }; });
  const reqs = await api("c", "/api/v1/spare-requests?pageSize=100", { headers: authHeaders() })
    .catch(e => { errs.reqs = e.message; return { items: [] }; });
  return { orders: state.orders || [], warns: state.warnings || [],
    parts: parts.items || [], reqs: reqs.items || [], errs };
}

/* ---------- 页面 ---------- */
registerPage("workbench", {
  async load(){
    const d = await wbLoadData();
    const user = state.user || {};
    const roles = (user.roleCodes || []).filter(c => WB_ROLES.some(r => r[0] === c));

    /* 汇总 */
    let total = 0, worst = null;
    const secHtml = roles.map(role => {
      const todos = wbRoleTodos(role, d);
      const counted = todos.filter(t => t.count != null);
      total += counted.reduce((s, t) => s + t.count, 0);
      todos.forEach(t => { if (t.tone === "bad" && !worst) worst = t; });
      return '<div class="card mt">'
        + sect(wbRoleZh(role) + "视角", todos.length ? counted.length + " 类待办" : "")
        + (todos.length
          ? '<div class="btn-group" style="flex-direction:column;align-items:stretch;gap:0">'
            + todos.map(wbItem).join('<div style="border-top:1px dashed var(--line)"></div>')
            + "</div>"
          : emptyBox("今日无待办 ✓", "该角色视角下当前没有需要处理的事项。"))
        + "</div>";
    }).join("");

    const head = '<div class="hdr"><div><h1>' + h("今日工作台")
      + hintMark("按角色聚合的待办，按「优先级 × 状态时效」规则排序（非预测）；每一项都来自 A/B/C/D 实时数据，点击「查看 →」直达对应页面。") + '</h1></div></div>'
      + '<div class="grid g4 mt">'
      + kpi("cyan", "我的角色", roles.length, roles.map(wbRoleZh).join(" · ") || "—")
      + kpi(total ? "yellow" : "green", "今日待办", total + " 项", total ? "各角色待办合计" : "全部清零")
      + kpi(worst ? "red" : "green", "最高风险项", worst ? worst.title : "无", worst ? "点击对应待办直接处置" : "无进行中的高风险事项")
      + kpi("dim", "排序方式", "规则排序", "优先级 × 状态时效 · 非预测")
      + "</div>";

    const body = roles.length
      ? secHtml
      + (d.errs.parts || d.errs.reqs
        ? noticeWarn("备件数据不可达：" + h(d.errs.parts || d.errs.reqs) + " —— 库管视角的待办可能不完整。")
        : "")
      + noticeLive("待办来自实时数据（工单 / 预警 / 备件申请 / 备件台账），"
        + "按登录角色（<span class=\"mono\">" + h(roles.join(", ")) + "</span>）聚合；"
        + "排序为规则排序（优先级 × 状态时效），本页不做预测与打分。")
      : emptyBox("当前角色无预置视图", "登录用户的角色（<span class=\"mono\">"
        + h((user.roleCodes || []).join(", ") || "无") + "</span>）不在工作台预置清单内。"
        + "可直接使用左侧导航进入各功能页。");

    return head + body;
  },
});
