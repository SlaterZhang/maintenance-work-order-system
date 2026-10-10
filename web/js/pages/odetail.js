/* 工单详情 —— 流转时间线（audit_log 驱动）· 可执行动作 · 维修结论 · 关联备件
   真实接口：C GET /api/v1/work-orders/{orderId}、POST /{orderId}/commands、
             POST /work-orders/{orderId}/spare-requests、GET /spare-requests?orderId= */
"use strict";

registerPage("odetail", {
  async load(ctx){
    const orderId = ctx.params.orderId;
    if (!orderId) return pageHdr("工单详情") + emptyBox("缺少工单号", "请从工单列表或看板点击进入");
    state.openOrder = orderId;
    await loadCore();
    await loadOrderExtras(orderId);
    return odetailHtml(orderId);
  },
  after(){ state._openForm = null; },
  async poll(ctx){
    const orderId = ctx.params.orderId;
    if (!orderId || !document.getElementById("od-status")) return;
    await loadOrders();
    await loadOrderExtras(orderId);
    const el = document.getElementById("od-body");
    if (el && !state._openForm) el.innerHTML = odetailBody(orderId);
  },
});

/** 工单详情专属数据：审计轨迹 + 关联备件申请 */
async function loadOrderExtras(orderId){
  state.orderAudit = [];
  state.orderRequests = [];
  try {
    const d = await api("c", "/api/v1/audit-logs?orderId=" + encodeURIComponent(orderId)
      + "&pageSize=100", { headers: authHeaders() });
    state.orderAudit = (d.items || []).slice().sort((a, b) =>
      String(a.createdAt).localeCompare(String(b.createdAt)));
  } catch (e) { /* 轨迹可降级 */ }
  try {
    const r = await api("c", "/api/v1/spare-requests?orderId=" + encodeURIComponent(orderId)
      + "&pageSize=100", { headers: authHeaders() });
    state.orderRequests = r.items || [];
  } catch (e) { /* 备件可降级 */ }
}

function odetailHtml(orderId){
  const o = (state.orders || []).find(x => x.orderId === orderId);
  if (!o) {
    return pageHdr("工单详情 · " + h(orderId))
      + noticeWarn("工单 " + h(orderId) + " 不在当前快照中。")
      + emptyBox("未找到该工单", "C 服务 GET /api/v1/work-orders/" + h(orderId) + " 可能返回 404")
      + '<div class="mt"><button class="btn" onclick="navigate(\'orders\')">← 返回工单列表</button></div>';
  }
  return pageHdr("工单详情 · " + h(o.orderId),
      h(o.equipmentId || "") + " · " + h(o.title || "") + " · " + o.priority,
      '<button class="btn btn-ghost btn-sm" onclick="refreshCurrent()">↻ 刷新</button>'
      + '<button class="btn btn-p btn-sm" onclick="openCreateSpareRequestModal(\''
        + h(o.orderId) + '\')">+ 申请备件</button>')
    + '<div id="od-body">' + odetailBody(orderId) + '</div>';
}

function odetailBody(orderId){
  const o = (state.orders || []).find(x => x.orderId === orderId);
  if (!o) return emptyBox("工单已不存在");
  const permSet = new Set((state.user && state.user.permissions) || []);
  const allowed = (TRANSITIONS[o.status] || []).filter(a =>
    permSet.has("ADMIN_ALL") || permSet.has(ACTION_META[a].perm));
  const overdue = o.dueAt && new Date(o.dueAt) < new Date()
    && !["COMPLETED","CANCELLED"].includes(o.status);
  const remaining = o.dueAt ? (new Date(o.dueAt) - new Date()) : null;

  let html = noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/work-orders/{orderId}</span>、"
    + "<span class=\"mono\">POST /{orderId}/commands</span>；流转时间线由 <span class=\"mono\">audit_log</span> 表驱动"
    + "（列 action / operator / before_value / after_value / detail / trace_id / created_at）。");

  // ---- 四张状态卡 ----
  html += '<div class="grid g4 mt">'
    + '<div class="card"><div class="mini">当前状态</div>'
    + '<div id="od-status" style="font-size:24px;font-weight:700;margin:6px 0;color:'
    + toneColor(enumTone("workOrderStatus", o.status)) + '">'
    + enumZh("workOrderStatus", o.status) + '</div>'
    + '<div class="mini mono">v' + h(o.version) + ' · ' + h(o.status) + '</div></div>'
    + '<div class="card"><div class="mini">优先级</div>'
    + '<div style="font-size:24px;font-weight:700;margin:6px 0">' + h(o.priority) + '</div>'
    + '<div class="mini">SLA ' + slaHours(o.priority) + 'h</div></div>'
    + '<div class="card"><div class="mini">负责人</div>'
    + '<div style="font-size:24px;font-weight:700;margin:6px 0">'
    + (o.assigneeId ? h(o.assigneeId) : '<span class="mini">未指派</span>') + '</div>'
    + '<div class="mini">' + h((state.equipment || []).map(e => e.equipmentId === o.equipmentId ? (e.responsibleDepartment || "") : "").join("") || "—") + '</div></div>'
    + '<div class="card"><div class="mini">' + (overdue ? "已超期" : "剩余时间") + '</div>'
    + '<div style="font-size:24px;font-weight:700;margin:6px 0;color:'
      + toneColor(overdue ? "bad" : "ok") + '">'
    + (remaining === null ? "—"
        : (overdue ? relTime(o.dueAt).replace("前", "前")
                   : fmtMinutes(Math.max(0, Math.round(remaining / 60000))))) + '</div>'
    + '<div class="mini">截止 ' + (o.dueAt ? fmtTime(o.dueAt) : "—") + '</div></div>'
    + '</div>';

  html += '<div class="grid g-2-1 mt">';

  // ---- 流转时间线 ----
  html += '<div class="card">' + sect("流转时间线", "audit_log")
    + odTimelineHtml(o) + '</div>';

  // ---- 可执行动作 ----
  html += '<div class="card">' + sect("可执行动作", "按权限动态渲染")
    + odActionsHtml(o, allowed)
    + '<div class="mini" style="margin-top:10px;line-height:1.8">'
    + '前端只做引导与劳效，真正的拦截在服务端——非法迁移返回结构化错误，'
    + '越权返回权限错误；传入的 operatorId 不被服务端信任，操作人由 JWT 身份决定。</div>'
    + '</div></div>';

  // ---- 工单信息 + 结论 ----
  html += '<div class="grid g2 mt">';
  html += '<div class="card">' + sect("工单信息")
    + '<table><tbody>'
    + '<tr><td style="width:110px">工单号</td><td class="mono">' + h(o.orderId) + '</td></tr>'
    + '<tr><td>来源类型</td><td>' + enumZh("workOrderSource", o.sourceType) + '</td></tr>'
    + '<tr><td>来源预警</td><td>' + (o.warningId
        ? '<a class="mono" style="color:var(--cyan);cursor:pointer" onclick="navigate(\'warn/'
          + h(o.warningId) + '\')">' + h(o.warningId) + '</a>'
        : '<span class="mini">—</span>') + '</td></tr>'
    + '<tr><td>设备</td><td>' + h(o.equipmentId || "—") + '</td></tr>'
    + '<tr><td>标题</td><td>' + h(o.title || "—") + '</td></tr>'
    + '<tr><td>描述</td><td>' + h(o.description || "—") + '</td></tr>'
    + '<tr><td>优先级</td><td>' + tag("workOrderPriority", o.priority) + '</td></tr>'
    + '<tr><td>创建人</td><td>' + h(o.reporterId || "—")
      + (o.sourceType === "WARNING" ? ' <span class="mini">（预警链路）</span>' : "") + '</td></tr>'
    + '<tr><td>负责人</td><td>' + h(o.assigneeId || "未指派") + '</td></tr>'
    + '<tr><td>创建时间</td><td>' + fmtTimeSec(o.createdAt) + '</td></tr>'
    + '<tr><td>截止时间</td><td>' + (o.dueAt ? fmtTimeSec(o.dueAt) : "—") + '</td></tr>'
    + '<tr><td>版本</td><td class="mono">v' + h(o.version) + '</td></tr>'
    + '</tbody></table></div>';

  const c = o.conclusion;
  html += '<div class="card">' + sect("维修结论", "回写 B 服务")
    + (c
        ? '<table><tbody>'
          + '<tr><td style="width:120px">根本原因</td><td>' + h(c.rootCause || "—") + '</td></tr>'
          + '<tr><td>处理措施</td><td>' + h(c.measures || "—") + '</td></tr>'
          + '<tr><td>维修结果</td><td>' + tag("maintenanceResult", c.result) + '</td></tr>'
          + '<tr><td>是否有效</td><td>' + (c.effective
              ? '<span style="color:' + toneColor("ok") + '">是</span>'
              : '<span style="color:' + toneColor("bad") + '">否</span>') + '</td></tr>'
          + '<tr><td>完成时间</td><td>' + fmtTimeSec(c.completedAt) + '</td></tr>'
          + '</tbody></table>'
          + '<div class="mini" style="margin-top:10px;line-height:1.8">'
          + '结论通过 <span class="mono">MaintenanceConclusionReported</span>（C-INT-05）回写 B，'
          + '驱动预警状态迁移：RECOVERED → RESOLVED；PARTIALLY_RECOVERED → HOLD_ACKNOWLEDGED；'
          + 'NOT_RECOVERED → 不变更状态。</div>'
        : noticeInfo("该工单尚未提交维修结论。")
          + '<div class="mini" style="line-height:1.8">在「提交验收」动作里填写根因 / 措施 / 结果 / 是否有效，'
          + '这四个字段会作为 <span class="mono">MaintenanceConclusionReported</span> 事件回写 B，'
          + '驱动预警状态迁移。</div>')
    + '</div></div>';

  // ---- 关联备件 ----
  const reqs = state.orderRequests || [];
  html += '<div class="card mt">' + sect("关联备件申请", reqs.length + " 条")
    + (reqs.length
        ? table(["申请号","备件","申请数","已发","状态","申请人","操作"], reqs.map(r => [
            '<span class="mono">' + h(r.requestId) + '</span>',
            '<span class="mono">' + h(r.sparePartId) + '</span>'
              + '<span class="mini"> ' + h(spareName(r.sparePartId)) + '</span>',
            h(r.requestedQuantity),
            h(r.issuedQuantity),
            tag("spareRequestStatus", r.status),
            h(r.requesterId || "—"),
            '<button class="btn btn-ghost btn-sm" onclick="navigate(\'sr\')">详情</button>',
          ]))
        : emptyBox("暂无备件申请", "可在本页右上「+ 申请备件」为该工单领用备件")
          + '<div class="mt"><button class="btn btn-sm" onclick="openCreateSpareRequestModal(\''
            + h(o.orderId) + '\')">+ 申请备件</button></div>')
    + '</div>';

  return html;
}

/** 按优先级返回 SLA 小时数 */
function slaHours(p){
  return ({ P1: 12, P2: 24, P3: 72, P4: 168 })[p] || 24;
}

function spareName(id){
  const sp = (state.spareParts || []).find(x => x.sparePartId === id);
  return sp ? sp.name : "";
}

/** 流转时间线：由 audit_log 的 action 推导每个节点的中文说明 */
// 键名必须与 C 服务实际写入 audit_log.action 的值逐字一致。
// 来源：apps/maintenance/src/application/work_order_service.py 的 _audit() 调用点
//   :275  f"COMMAND:{action.value}"   ← 注意是冒号，不是下划线
//   :129  "AUTO_CREATE_FROM_WARNING"
//   :173  "CREATE_MANUAL"
//   :354  "AUTO_CLOSE_ON_WARNING_RESOLVED"
//   :362  "AUTO_CLOSE_SKIPPED"
// 九条命令动作值取自 apps/maintenance/src/domain/enums.py 的 WorkOrderAction 枚举。
const OD_ACTION_ZH = {
  "COMMAND:CONFIRM": { z:"确认工单", ic:"●" },
  "COMMAND:ASSIGN": { z:"派单", ic:"●" },
  "COMMAND:ACCEPT": { z:"接单", ic:"●" },
  "COMMAND:START": { z:"开始维修", ic:"●" },
  "COMMAND:WAIT_FOR_PARTS": { z:"等待备件", ic:"●" },
  "COMMAND:RESUME": { z:"恢复维修", ic:"●" },
  "COMMAND:SUBMIT_FOR_INSPECTION": { z:"提交验收", ic:"●" },
  "COMMAND:PASS_INSPECTION": { z:"验收通过", ic:"●" },
  "COMMAND:REJECT_INSPECTION": { z:"验收驳回", ic:"●" },
  "COMMAND:CANCEL": { z:"取消工单", ic:"●" },
  AUTO_CREATE_FROM_WARNING: { z:"预警自动建单", ic:"○" },
  CREATE_MANUAL: { z:"人工报修建单", ic:"○" },
  AUTO_CLOSE_ON_WARNING_RESOLVED: { z:"设备恢复，系统自动结单", ic:"○" },
  AUTO_CLOSE_SKIPPED: { z:"设备已恢复但工单已进维修，留人工流程", ic:"○" },
};
// 备件申请流水不走 audit_log（spare_service.py 未写审计），此处仅供备件页复用。
const OD_SPARE_ACTION_ZH = {
  APPROVE: "主管审批", REJECT: "审批驳回", RESERVE: "库存预留",
  ISSUE: "库房发料", RETURN: "退料", CLOSE: "关单", CANCEL: "取消",
};

function odTimelineHtml(o){
  const audit = state.orderAudit || [];
  let html = orderFlowStepsHtml(o);
  if (!audit.length) {
    return html + '<div class="mt">' + emptyBox("暂无审计轨迹",
      "C 服务 GET /api/v1/audit-logs?orderId=" + h(o.orderId) + " 未返回记录") + '</div>';
  }
  // 结构对齐 web/css/platform.css:223-232 的竖向时间线：
  // 容器 .timeline，条目 .tl(+状态类)，子元素 .tt/.td/.tm。
  html += '<div class="timeline mt">';
  audit.forEach(a => {
    const meta = OD_ACTION_ZH[a.action] || { z: a.action, ic:"○" };
    const isAuto = /^(AUTO_|CREATE_MANUAL)/.test(a.action) && !/^COMMAND:/.test(a.action);
    const tone = a.action === "AUTO_CLOSE_SKIPPED" ? "warn" : (isAuto ? "ok" : "");
    html += '<div class="tl' + (tone ? " " + tone : "") + '">'
      + '<div class="tt">' + h(meta.z)
      + ' <span class="mini">' + h(a.operatorId || "系统") + '</span>'
      + (isAuto ? ' <span class="pill b-purple">系统自动</span>' : "")
      + ' <span class="tm">' + fmtTimeSec(a.createdAt) + '</span>'
      + '</div>'
      + ((a.beforeValue || a.afterValue)
          ? '<div class="td mono">' + h(a.beforeValue || "—") + ' → ' + h(a.afterValue || "—") + '</div>'
          : "")
      + (a.detail ? '<div class="td">' + h(a.detail) + '</div>' : "")
      + (a.traceId ? '<div class="tm">' + h(a.traceId) + '</div>' : "")
      + '</div>';
  });
  html += '</div>';
  return html;
}

/** 横向流程步骤条（当前停留位置） */
function orderFlowStepsHtml(o){
  const flow = [
    { z:"待确认", s:["PENDING_CONFIRMATION"] },
    { z:"待派单", s:["PENDING_ASSIGNMENT","PENDING_ACCEPTANCE"] },
    { z:"维修中", s:["PENDING_MAINTENANCE","MAINTAINING","WAITING_PARTS"] },
    { z:"待验收", s:["PENDING_INSPECTION"] },
    { z:"已完成", s:["COMPLETED"] },
  ];
  const idx = flow.findIndex(g => g.s.includes(o.status));
  let html = '<div class="tl-steps">';
  flow.forEach((g, i) => {
    let cls = "";
    if (i < idx) cls = "done";
    else if (i === idx) cls = o.status === "COMPLETED" ? "done" : "active";
    html += '<div class="tl-step ' + cls + '">' + g.z + '</div>';
  });
  if (o.status === "CANCELLED") html += '<div class="tl-step active cancelled">已取消</div>';
  html += '</div>';
  return html;
}

/** 动作区：按钮 + 表单容器 */
function odActionsHtml(o, allowed){
  if (!allowed.length) {
    const why = o.status === "COMPLETED" ? "工单已完成归档"
      : o.status === "CANCELLED" ? "工单已取消"
      : "当前登录角色在此状态下无可用操作（缺对应权限码）";
    return '<div class="mini">' + why + '</div>';
  }
  let html = '<div class="li" style="gap:8px;flex-wrap:wrap">';
  allowed.forEach(a => {
    const meta = ACTION_META[a];
    html += '<button class="btn btn-' + meta.kind + ' btn-sm" onclick="openOrderActionForm(\''
      + h(o.orderId) + '\',\'' + a + '\')">' + h(meta.label) + '</button>';
  });
  html += '</div><div id="od-opform" class="opform mt" style="display:none"></div>';
  return html;
}

/** 展开动作表单（派单选人来自 D 服务；提交验收填结论） */
async function openOrderActionForm(orderId, action){
  const box = document.getElementById("od-opform");
  const o = (state.orders || []).find(x => x.orderId === orderId);
  if (!box || !o) return;
  const btn = '<button class="btn btn-sm" onclick="runOrderAction(\'' + h(orderId)
    + '\',\'' + action + '\')">执行</button>'
    + '<button class="btn btn-ghost btn-sm" onclick="closeOrderActionForm()">取消</button>';

  if (action === "ASSIGN") {
    const engineers = await ensureAssignees();
    box.innerHTML = '<div class="mini">派单给（工程师列表来自 D 服务）</div>'
      + '<select id="f-assignee" class="inp" style="max-width:280px">'
      + (engineers.length
          ? engineers.map(u => '<option value="' + h(u.userId) + '">' + h(u.userId) + ' · '
              + h(u.displayName) + '</option>').join("")
          : '<option value="">（工程师列表不可用）</option>')
      + '</select><div style="margin-top:8px">' + btn + '</div>';
  } else if (action === "SUBMIT_FOR_INSPECTION") {
    box.innerHTML = '<div class="mini">根因 / 措施 / 结果（回写 B 的维修结论）</div>'
      + '<input id="f-root" class="inp" style="width:100%;max-width:520px" placeholder="根因（如：主轴轴承润滑不足导致振动升高）">'
      + '<input id="f-measure" class="inp mt" style="width:100%;max-width:520px" placeholder="措施（如：补润滑换轴承，完成试运行）">'
      + '<select id="f-result" class="inp" style="max-width:220px">'
      + '<option value="RECOVERED">RECOVERED · 已恢复</option>'
      + '<option value="PARTIALLY_RECOVERED">PARTIALLY_RECOVERED · 部分恢复</option>'
      + '<option value="NOT_RECOVERED">NOT_RECOVERED · 未恢复</option></select>'
      + '<label class="li" style="gap:6px;cursor:pointer"><input type="checkbox" id="f-restore-eq" checked>'
      + '<span class="mini">验收通过后自动将设备恢复为正常运转</span></label>'
      + '<div style="margin-top:8px">' + btn + '</div>';
  } else if (action === "PASS_INSPECTION") {
    box.innerHTML = '<label class="li" style="gap:6px;cursor:pointer">'
      + '<input type="checkbox" id="f-restore-eq" checked>'
      + '<span class="mini">验收通过后自动将设备恢复为正常运转</span></label>'
      + '<div style="margin-top:8px">' + btn + '</div>';
  } else if (action === "REJECT_INSPECTION") {
    box.innerHTML = '<input id="f-comment" class="inp" style="width:100%;max-width:520px" placeholder="驳回原因（必填，如：试运行振动超标）">'
      + '<div style="margin-top:8px">' + btn + '</div>';
  } else if (action === "CANCEL") {
    box.innerHTML = '<input id="f-comment" class="inp" style="width:100%;max-width:520px" placeholder="取消原因（可选）">'
      + '<div style="margin-top:8px">' + btn + '</div>';
  } else {
    box.innerHTML = '<div class="mini">该动作无需额外参数。</div><div style="margin-top:8px">' + btn + '</div>';
  }
  box.style.display = "block";
  state._openForm = { orderId: orderId, action: action };
}

function closeOrderActionForm(){
  const box = document.getElementById("od-opform");
  if (box) { box.style.display = "none"; box.innerHTML = ""; }
  state._openForm = null;
}

/** 执行动作：组装 body（含结论与恢复设备开关）后调 submitOrderCommand */
async function runOrderAction(orderId, action){
  const o = (state.orders || []).find(x => x.orderId === orderId);
  if (!o) { toast("工单已不存在，请刷新", "err"); return; }
  const val = id => ((document.getElementById(id) || {}).value || "");
  const extra = {};

  if (action === "ASSIGN") {
    const a = val("f-assignee");
    if (!a) { toast("请选择派单工程师", "err"); return; }
    extra.assigneeId = a;
  } else if (action === "SUBMIT_FOR_INSPECTION") {
    const root = val("f-root").trim(), meas = val("f-measure").trim();
    if (!root) { toast("请填写根因", "err"); return; }
    if (!meas) { toast("请填写措施", "err"); return; }
    const cb = document.getElementById("f-restore-eq");
    extra._restoreEquipment = cb ? cb.checked : true;
    extra.conclusion = {
      rootCause: root, measures: meas,
      result: val("f-result") || "RECOVERED",
      effective: true, completedAt: nowIso(),
    };
  } else if (action === "PASS_INSPECTION") {
    const cb = document.getElementById("f-restore-eq");
    extra._restoreEquipment = cb ? cb.checked : true;
  } else if (action === "REJECT_INSPECTION") {
    const c = val("f-comment").trim();
    if (!c) { toast("请填写驳回原因", "err"); return; }
    extra.comment = c;
  } else if (action === "CANCEL") {
    const c = val("f-comment").trim();
    if (c) extra.comment = c;
    const ok = await confirmBox("取消工单", "取消仅允许早三态（待确认 / 待派单 / 待接单）。"
      + "一旦进入维修，取消会掩盖已发生的维修成本，服务端会拒绝。确定取消？", { danger: true });
    if (!ok) return;
  }
  closeOrderActionForm();
  await submitOrderCommand(o, action, extra);
}

/** 为该工单申请备件 */
async function openCreateSpareRequestModal(orderId){
  if (!state.spareParts || !state.spareParts.length) await loadSpareParts();
  const html = '<div class="field"><div class="mini">备件 *</div>'
    + '<select id="sr-part" class="inp" style="width:100%">'
    + (state.spareParts || []).map(s => '<option value="' + h(s.sparePartId) + '">'
        + h(s.sparePartId) + ' · ' + h(s.name) + '（可用 ' + s.availableQuantity + h(s.unit) + '）</option>').join("")
    + '</select></div>'
    + '<div class="field mt"><div class="mini">申请数量 *</div>'
    + '<input id="sr-qty" class="inp" type="number" min="1" value="1" style="width:100%"></div>'
    + '<div class="field mt"><div class="mini">事由</div>'
    + '<input id="sr-reason" class="inp" style="width:100%" placeholder="如：主轴轴承异响需更换"></div>'
    + '<div class="mini mt" style="line-height:1.7">备件申请必须挂在具体工单下，不能凭空领料；'
    + '审批人、发料人、申请人必须是不同角色，避免一个人走完整个流程。</div>';
  openModal("申请备件 · " + orderId, html, {
    width: 520,
    footer: '<button class="btn btn-ghost" onclick="closeModal()">取消</button>'
      + '<button class="btn" onclick="submitSpareRequest(\'' + h(orderId) + '\')">提交申请</button>',
  });
}

async function submitSpareRequest(orderId){
  const partId = (document.getElementById("sr-part") || {}).value;
  const qty = parseInt((document.getElementById("sr-qty") || {}).value, 10);
  const reason = ((document.getElementById("sr-reason") || {}).value || "").trim();
  if (!partId) { toast("请选择备件", "err"); return; }
  if (!qty || qty < 1) { toast("申请数量必须大于 0", "err"); return; }
  try {
    const r = await api("c", "/api/v1/work-orders/" + encodeURIComponent(orderId) + "/spare-requests", {
      method: "POST",
      headers: Object.assign(authHeaders(), { "Idempotency-Key": uuidv4() }),
      body: {
        sparePartId: partId, requestedQuantity: qty,
        requesterId: (state.user && state.user.userId) || "", reason: reason || null,
      },
    });
    closeModal();
    log("申请备件", r.requestId + " · " + partId + " × " + qty, true);
    toast("备件申请已提交：" + r.requestId, "ok");
    await loadOrderExtras(orderId);
    await route(true);
  } catch (e) {
    log("申请备件", e.message, false);
    toast("申请失败：" + e.message, "err");
  }
}
