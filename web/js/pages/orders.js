/* 工单列表 —— 表格视图 · 批量筛选与导出 · 工单动作（含结论表单）
   真实接口：C GET /api/v1/work-orders、POST /api/v1/work-orders、
             POST /api/v1/work-orders/{orderId}/commands；
             派单选人来自 D GET /api/v1/users?roleCodes=MAINTENANCE_ENGINEER */
"use strict";

registerPage("orders", {
  async load(){ await loadCore(); state.orderFilter = state.orderFilter || {}; return null; },
  render(){ return pageHdr("工单列表", "表格视图 · 批量筛选与导出 · 行内可执行工单动作", ordersToolbar())
    + ordersBody(); },
  async poll(){
    if (!document.getElementById("orders-tbl")) return;
    await loadOrders();
    const el = document.getElementById("orders-tbl");
    if (el && !state._openForm) el.innerHTML = ordersTableHtml();
  },
});

function ordersToolbar(){
  return '<button class="btn btn-ghost btn-sm" onclick="exportOrdersCsv()">⇩ 导出 CSV</button>'
    + '<button class="btn btn-p btn-sm" onclick="navigate(\'kanban\')">▤ 看板视图</button>'
    + '<button class="btn btn-sm" onclick="openCreateOrderModal()">+ 新建工单</button>';
}

function ordersFiltered(){
  const f = state.orderFilter || {};
  let list = state.orders || [];
  if (f.status) list = list.filter(o => o.status === f.status);
  if (f.priority) list = list.filter(o => o.priority === f.priority);
  if (f.source) list = list.filter(o => o.sourceType === f.source);
  if (f.kw) {
    const k = f.kw.toLowerCase();
    list = list.filter(o => (o.orderId + " " + (o.equipmentId || "") + " "
      + (o.title || "")).toLowerCase().indexOf(k) >= 0);
  }
  return list;
}

function ordersBody(){
  const all = state.orders || [];
  const open = openOrders();
  const done = all.filter(o => o.status === "COMPLETED");
  const overdue = open.filter(o => o.dueAt && new Date(o.dueAt) < new Date());
  const withTime = done.filter(o => o.createdAt && o.updatedAt);
  const avgH = withTime.length
    ? (withTime.reduce((s, o) => s + (new Date(o.updatedAt) - new Date(o.createdAt)) / 3600000, 0)
       / withTime.length)
    : null;

  let html = noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/work-orders</span>"
    + "（本页与「工单看板」共用同一份数据，区别在于形态：看板看流程位置，列表看字段明细）。"
    + "工单动作走 <span class=\"mono\">POST /work-orders/{orderId}/commands</span>，"
    + "每个动作校验独立权限码，非法迁移由服务端状态机拒绝。");

  html += '<div class="grid g5 mt">'
    + kpi("cyan", "工单总数", all.length, "含历史")
    + kpi("ok", "已完成", done.length, "含自动结单")
    + kpi("warn", "未结", open.length, "其中 P1 " + open.filter(o => o.priority === "P1").length + " 张")
    + kpi("purple", "平均处理时长", avgH === null ? "—" : fmtNum(avgH, 1) + " h", "目标 &lt;6h")
    + kpi(overdue.length ? "bad" : "ok", "超期风险", overdue.length, overdue.length ? "需优先处理" : "当前无超期")
    + '</div>';

  // ---- 筛选器 ----
  const f = state.orderFilter || {};
  html += '<div class="card mt">'
    + '<div class="li" style="gap:8px;flex-wrap:wrap;margin-bottom:10px">'
    + '<input id="of-kw" class="inp" style="max-width:220px" placeholder="⌕ 工单号 / 设备 / 标题" value="'
      + h(f.kw || "") + '" onkeydown="if(event.key===\'Enter\')applyOrderFilter()">'
    + selectHtml("of-status", [["","全部状态"]].concat(
        Object.keys(ENUMS.workOrderStatus || {}).map(s => [s, enumZh("workOrderStatus", s)])), f.status, "applyOrderFilter()")
    + selectHtml("of-priority", [["","全部优先级"],["P1","P1"],["P2","P2"],["P3","P3"],["P4","P4"]],
        f.priority, "applyOrderFilter()")
    + selectHtml("of-source", [["","全部来源"]].concat(
        Object.keys(ENUMS.workOrderSource || {}).map(s => [s, enumZh("workOrderSource", s)])), f.source, "applyOrderFilter()")
    + '<button class="btn btn-sm" onclick="applyOrderFilter()">查询</button>'
    + '<button class="btn btn-ghost btn-sm" onclick="resetOrderFilter()">重置</button>'
    + '<span class="spacer" style="flex:1"></span>'
    + '<span class="mini">共 ' + ordersFiltered().length + ' 条</span>'
    + '</div>'
    + '<div id="orders-tbl">' + ordersTableHtml() + '</div>'
    + '</div>';

  // ---- 来源构成 + 停留时长 + 超期 ----
  html += '<div class="grid g3 mt">';
  const srcCount = {};
  all.forEach(o => { srcCount[o.sourceType] = (srcCount[o.sourceType] || 0) + 1; });
  html += '<div class="card">' + sect("工单来源构成", "近 30 天")
    + bars(Object.keys(srcCount).map(s => ({
        label: enumZh("workOrderSource", s), value: srcCount[s],
        tone: s === "WARNING" ? "cyan" : s === "MANUAL" ? "purple" : "ok",
      })), null, " 张")
    + '<div class="mini" style="margin-top:10px;line-height:1.8">预警自动建单是「监测→预警→工单」闭环的直接体现；'
    + '人工报修与巡检发现说明现场经验仍然重要，两者不可互相替代。</div></div>';

  const stCount = {};
  open.forEach(o => { stCount[o.status] = (stCount[o.status] || 0) + 1; });
  html += '<div class="card">' + sect("未结工单状态分布", open.length + " 张")
    + bars(Object.keys(stCount).map(s => ({
        label: enumZh("workOrderStatus", s), value: stCount[s], tone: enumTone("workOrderStatus", s),
      })), null, " 张") + '</div>';

  html += '<div class="card">' + sect("超期风险与积压", "需优先处理")
    + (overdue.length
        ? overdue.slice(0, 6).map(o => '<div style="margin-bottom:9px">'
            + '<div class="li" style="justify-content:space-between">'
            + '<span class="l1 mono">' + h(o.orderId) + ' ' + tag("workOrderPriority", o.priority) + '</span>'
            + '<span class="lv" style="color:' + toneColor("bad") + '">'
            + relTime(o.dueAt) + '</span></div>'
            + '<div class="mini">' + h(o.equipmentId || "") + ' · '
            + enumZh("workOrderStatus", o.status) + '<span class="mini"> · ' + h(o.assigneeId || "未指派") + '</span></div>'
            + '</div>').join("")
        : emptyBox("当前没有超期工单", "超期定义：dueAt 早于当前时间且未完成/未取消"))
    + '</div></div>';

  return html;
}

/** 简单下拉：opts = [[value, label], ...] */
function selectHtml(id, opts, cur, onchange){
  return '<select id="' + id + '" class="inp" style="max-width:150px" onchange="' + onchange + '">'
    + opts.map(o => '<option value="' + h(o[0]) + '"'
        + (String(cur || "") === String(o[0]) ? " selected" : "") + '>' + h(o[1]) + '</option>').join("")
    + '</select>';
}

function ordersTableHtml(){
  const list = ordersFiltered();
  if (!list.length) {
    return emptyBox("暂无工单", "可点右上「+ 新建工单」人工报修，或到设备详情注入异常让 B 自动建单");
  }
  const permSet = new Set((state.user && state.user.permissions) || []);
  const rows = list.map(o => {
    const eq = (state.equipment || []).find(e => e.equipmentId === o.equipmentId);
    const allowed = (TRANSITIONS[o.status] || []).filter(a =>
      permSet.has("ADMIN_ALL") || permSet.has(ACTION_META[a].perm));
    const od = o.dueAt && new Date(o.dueAt) < new Date()
      && !["COMPLETED","CANCELLED"].includes(o.status);
    return [
      '<label style="display:flex;align-items:center;gap:6px">'
        + '<input type="checkbox" class="ord-ck" value="' + h(o.orderId) + '" style="cursor:pointer">'
        + '<a class="mono" style="color:var(--cyan);cursor:pointer" onclick="navigate(\'order/'
        + h(o.orderId) + '\')">' + h(o.orderId) + '</a></label>',
      h(o.equipmentId || "—") + (eq ? ' <span class="mini">' + h(eq.name) + '</span>' : ""),
      tag("workOrderPriority", o.priority),
      tag("workOrderStatus", o.status),
      enumZh("workOrderSource", o.sourceType),
      o.warningId
        ? '<a class="mono mini" style="color:var(--cyan);cursor:pointer" onclick="navigate(\'warn/'
            + h(o.warningId) + '\')">' + h(o.warningId) + '</a>'
        : '<span class="mini">—</span>',
      o.assigneeId ? h(o.assigneeId) : '<span class="mini">未指派</span>',
      '<span class="mini">' + fmtTime(o.createdAt) + '</span>',
      '<span class="mini"' + (od ? ' style="color:' + toneColor("bad") + ';font-weight:600"' : "")
        + '>' + (o.dueAt ? fmtTime(o.dueAt) : "—") + '</span>',
      '<button class="btn btn-ghost btn-sm" onclick="navigate(\'order/' + h(o.orderId) + '\')">详情</button>'
        + (allowed.length ? ' <button class="btn btn-sm" onclick="quickOrderAction(\''
            + h(o.orderId) + '\',\'' + allowed[0] + '\')">'
            + h(ACTION_META[allowed[0]].label) + '</button>' : ""),
    ];
  });
  return '<div class="tbl-wrap"><table><thead><tr>'
    + ['<input type="checkbox" onchange="toggleAllOrders(this.checked)" style="cursor:pointer">',
       "工单号","设备","优先级","状态","来源","来源预警","负责人","创建时间","截止","操作"]
        .map(x => '<th>' + x + '</th>').join("")
    + '</tr></thead><tbody>'
    + rows.map(r => '<tr>' + r.map(c => '<td>' + c + '</td>').join("") + '</tr>').join("")
    + '</tbody></table></div>'
    + '<div class="li" style="gap:8px;margin-top:10px">'
    + '<button class="btn btn-ghost btn-sm" onclick="batchOrderAction(\'CONFIRM\')">批量确认</button>'
    + '<button class="btn btn-ghost btn-sm" onclick="exportOrdersCsv()">批量导出</button>'
    + '<span class="mini" id="ord-sel-count">已选 0 项</span></div>';
}

function toggleAllOrders(checked){
  document.querySelectorAll(".ord-ck").forEach(c => { c.checked = checked; });
  updateOrderSelCount();
}
function updateOrderSelCount(){
  const el = document.getElementById("ord-sel-count");
  if (el) el.textContent = "已选 " + document.querySelectorAll(".ord-ck:checked").length + " 项";
}
function selectedOrders(){
  return Array.from(document.querySelectorAll(".ord-ck:checked")).map(c => c.value);
}

function applyOrderFilter(){
  state.orderFilter = {
    kw: (document.getElementById("of-kw") || {}).value || "",
    status: (document.getElementById("of-status") || {}).value || "",
    priority: (document.getElementById("of-priority") || {}).value || "",
    source: (document.getElementById("of-source") || {}).value || "",
  };
  route(true);
}
function resetOrderFilter(){ state.orderFilter = {}; route(true); }

/** 列表页快捷动作：不带表单的动作直接执行，带表单的引导到详情页 */
async function quickOrderAction(orderId, action){
  const o = (state.orders || []).find(x => x.orderId === orderId);
  if (!o) return;
  if (ACTION_META[action] && ACTION_META[action].form) {
    navigate("order/" + orderId);
    toast("该动作需要填写表单，已跳转到工单详情", "ok");
    return;
  }
  await submitOrderCommand(o, action, {});
}

/** 批量确认（仅对 PENDING_CONFIRMATION 生效） */
async function batchOrderAction(action){
  const ids = selectedOrders();
  if (!ids.length) { toast("请先勾选工单", "err"); return; }
  const ok = await confirmBox("批量" + (ACTION_META[action] || {}).label,
    "将对选中的 " + ids.length + " 张工单执行「" + (ACTION_META[action] || {}).label + "」，"
    + "服务端会逐张校验状态与权限，不适用的会跳过。确定继续？");
  if (!ok) return;
  let done = 0, fail = 0;
  for (const id of ids) {
    const o = (state.orders || []).find(x => x.orderId === id);
    if (!o || !(TRANSITIONS[o.status] || []).includes(action)) { fail++; continue; }
    try { await submitOrderCommand(o, action, {}, true); done++; }
    catch (e) { fail++; }
  }
  toast("批量完成：成功 " + done + " 张，跳过/失败 " + fail + " 张", done ? "ok" : "err");
  await loadOrders();
  await route(true);
}

/** 统一命令提交入口（详情页与列表页共用） */
async function submitOrderCommand(o, action, extraBody, silent){
  const body = Object.assign({
    action: action,
    operatorId: (state.user && state.user.userId) || "",
    expectedVersion: o.version,
  }, extraBody || {});
  const restoreEq = body._restoreEquipment;
  delete body._restoreEquipment;
  try {
    const result = await api("c", "/api/v1/work-orders/" + encodeURIComponent(o.orderId) + "/commands", {
      method: "POST",
      headers: Object.assign(authHeaders(), { "Idempotency-Key": uuidv4() }),
      body: body,
    });
    if (!silent) {
      log("工单操作", action + " " + o.orderId + " → " + enumZh("workOrderStatus", result.status),
        true);
      toast(ACTION_META[action].label + "成功：" + enumZh("workOrderStatus", result.status), "ok");
    }
    // 验收通过且勾选「恢复设备」→ 通知 A 复位（并让 B 自动闭环预警）
    if (restoreEq && (action === "SUBMIT_FOR_INSPECTION" || action === "PASS_INSPECTION")
        && o.equipmentId) {
      await recoverEquipmentAfterMaintenance(o.equipmentId);
    }
    if (!silent) {
      await loadCore();
      await route(true);
    }
    return result;
  } catch (e) {
    if (!silent) {
      log("工单操作", action + " " + o.orderId + "：" + e.message, false);
      toast(ACTION_META[action].label + "失败：" + e.message, "err");
      await loadOrders();
      if (document.getElementById("orders-tbl")) {
        document.getElementById("orders-tbl").innerHTML = ordersTableHtml();
      }
    }
    throw e;
  }
}

/** 新建工单（弹窗表单，替代旧的行内表单） */
async function openCreateOrderModal(){
  await ensureAssignees();
  const eqOpts = (state.equipment || []).map(e =>
    '<option value="' + h(e.equipmentId) + '">' + h(e.equipmentId) + ' · ' + h(e.name || "") + '</option>').join("");
  const html = '<div class="field"><div class="mini">设备 *</div>'
    + '<select id="c-eq" class="inp" style="width:100%">' + eqOpts + '</select></div>'
    + '<div class="field mt"><div class="mini">标题 *</div>'
    + '<input id="c-title" class="inp" style="width:100%" placeholder="如：一号数控机床振动超标检查"></div>'
    + '<div class="field mt"><div class="mini">优先级</div>'
    + '<select id="c-priority" class="inp" style="width:100%">'
    + ["P1","P2","P3","P4"].map(p => '<option value="' + p + '"'
        + (p === "P2" ? " selected" : "") + '>' + p + ' · '
        + ({P1:"紧急",P2:"高",P3:"中",P4:"低"})[p] + '</option>').join("")
    + '</select></div>'
    + '<div class="mini mt" style="line-height:1.7">人工报修走 <span class="mono">sourceType=MANUAL</span>，'
    + '报修人取当前登录身份（契约必填，曾因漏传导致 500）。</div>';
  openModal("新建工单", html, {
    width: 520,
    footer: '<button class="btn btn-ghost" onclick="closeModal()">取消</button>'
      + '<button class="btn" onclick="submitNewOrder()">创建工单</button>',
    onOpen(){ const el = document.getElementById("c-title"); if (el) el.focus(); },
  });
}

async function submitNewOrder(){
  const eqId = (document.getElementById("c-eq") || {}).value;
  const title = ((document.getElementById("c-title") || {}).value || "").trim();
  const priority = (document.getElementById("c-priority") || {}).value || "P2";
  if (!eqId) { toast("请选择设备", "err"); return; }
  if (!title) { toast("请输入工单标题", "err"); return; }
  try {
    const result = await api("c", "/api/v1/work-orders", {
      method: "POST",
      headers: Object.assign(authHeaders(), { "Idempotency-Key": uuidv4() }),
      body: {
        equipmentId: eqId, title: title, description: title, priority: priority,
        sourceType: "MANUAL", reporterId: (state.user && state.user.userId) || "",
      },
    });
    closeModal();
    log("创建工单", "新工单 " + result.orderId + " 已创建（" + priority + "）", true);
    toast("工单创建成功：" + result.orderId, "ok");
    await loadOrders();
    await route(true);
  } catch (e) {
    log("创建工单", e.message, false);
    toast("创建工单失败：" + e.message, "err");
  }
}

/** 派单工程师列表（D 服务） */
async function ensureAssignees(){
  if (state.assignees && state.assignees.length) return state.assignees;
  try {
    const data = await api("d", "/api/v1/users?roleCodes=MAINTENANCE_ENGINEER&pageSize=100",
      { headers: authHeaders() });
    state.assignees = (data.items || []).filter(u => u.enabled);
  } catch (e) {
    state.assignees = [];
    toast("可派单工程师列表加载失败：" + e.message, "err");
  }
  return state.assignees;
}

function exportOrdersCsv(){
  const list = ordersFiltered();
  if (!list.length) { toast("没有可导出的工单", "err"); return; }
  downloadCsv("work-orders",
    ["工单号","设备","优先级","状态","来源","来源预警","负责人","标题","创建时间","截止","版本"],
    list.map(o => [o.orderId, o.equipmentId, o.priority, o.status, o.sourceType,
      o.warningId || "", o.assigneeId || "", o.title, o.createdAt, o.dueAt || "", o.version]));
}

/* 勾选框变化时更新计数（事件委托，避免内联 onclick 拼接） */
document.addEventListener("change", function (e) {
  if (e.target && e.target.classList && e.target.classList.contains("ord-ck")) {
    updateOrderSelCount();
  }
});
