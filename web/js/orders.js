/* 维修工单：列表/详情/操作表单/命令（P2-4 派单选人来自 D，P2-5 表单不预填台词，
   P2-7 事件委托消除 onclick 拼接的 XSS 面） */
"use strict";

/* P2-4：可派单工程师从 D-API-03 拉取（不再硬编码，也不把仓管员当工程师） */
async function ensureAssignees(){
  if (state.assignees) return state.assignees;
  try {
    const data = await api("d", "/api/v1/users?roleCodes=MAINTENANCE_ENGINEER&pageSize=100",
        {headers: authHeaders()});
    state.assignees = (data.items || []).filter(u => u.enabled);
  } catch (e) {
    state.assignees = [];
    toast("可派单工程师列表加载失败：" + e.message, "err");
  }
  return state.assignees;
}

function showCreateOrderForm(){
  const form = $("create-order-form");
  const select = $("new-eq");
  if (select.options.length <= 1) {
    state.equipment.forEach(eq => {
      const opt = document.createElement("option");
      opt.value = eq.equipmentId;
      opt.textContent = `${eq.equipmentId} - ${eq.name || eq.equipmentId}`;
      select.appendChild(opt);
    });
  }
  form.style.display = "flex";
  $("new-title").focus();
}

function hideCreateOrderForm(){
  $("create-order-form").style.display = "none";
  $("new-title").value = "";
  $("new-priority").value = "P2";
  $("new-eq").value = "";
}

async function createNewOrder(){
  const eqId = $("new-eq").value;
  const title = $("new-title").value.trim();
  const priority = $("new-priority").value.toUpperCase() || "P2";
  if (!eqId) { toast("请选择设备", "err"); return; }
  if (!title) { toast("请输入工单标题", "err"); return; }
  try {
    showStatus("📝 正在创建维修工单...");
    const result = await api("c", "/api/v1/work-orders", {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body:{
        equipmentId: eqId,
        title: title,
        description: title,   // 人工报修：描述默认同标题，可在后续处置中补充
        priority: priority,
        sourceType: "MANUAL",
        reporterId: (state.user && state.user.userId) || "",   // 报修人=登录者（契约必填，曾漏传致500）
      },
    });
    log("创建工单", `新工单 ${result.orderId} 已创建（${priority}）`, true);
    toast(`✅ 工单创建成功：${result.orderId}`, "ok");
    hideCreateOrderForm();
    await refreshOrders();
    showStatus("✅ 工单创建完成");
    setTimeout(hideStatus, 3000);
  } catch (e) {
    hideStatus();
    toast("创建工单失败：" + e.message, "err");
    log("创建工单", e.message, false);
  }
}

async function refreshOrders(){
  try {
    const data = await api("c", "/api/v1/work-orders?pageSize=50", {headers: authHeaders()});
    state.orders = data.items || [];   // C 按 createdAt 降序返回，最新单在前
    renderOrders();
  } catch (e) {
    toast("工单列表加载失败：" + e.message, "err");
  }
}

function renderOrders(){
  const body = $("orders-body");
  // 轮询重建前缓存填写中的操作表单，重建后还原，避免用户输入被冲掉
  if (state._openForm) {
    const of = $("opform-" + state._openForm.orderId);
    if (of && of.style.display !== "none") {
      const vals = {};
      of.querySelectorAll("input,select").forEach(el => { vals[el.id] = el.value; });
      state._openForm.values = vals;
    } else {
      state._openForm = null;
    }
  }
  body.innerHTML = "";
  if (!state.orders.length) {
    body.innerHTML = '<tr><td colspan="7"><div class="empty">暂无工单（可在设备详情页注入异常触发自动建单）</div></td></tr>';
    return;
  }
  for (const o of state.orders) {
    const tr = document.createElement("tr");
    tr.className = "order-row";
    tr.dataset.order = o.orderId;   // P2-7：行点击走事件委托，不再拼 onclick
    tr.innerHTML =
      `<td><b>${esc(o.orderId)}</b></td>` +
      `<td>${esc(o.equipmentId)}<div class="mini">${esc(o.equipmentNameSnapshot)}</div></td>` +
      `<td class="prio p-${esc(o.priority)}">${esc(o.priority)}</td>` +
      `<td><span class="pill s-${esc(o.status)}">${esc(STATUS_ZH[o.status] || o.status)}</span></td>` +
      `<td class="mini">${esc(o.warningId || "--")}</td>` +
      `<td class="mini">${esc((o.createdAt || "").replace("T"," ").slice(0,19))}</td>` +
      `<td class="mini">v${esc(o.version)}</td>`;
    body.appendChild(tr);
    if (state.expandedOrder === o.orderId) body.appendChild(orderPanelRow(o));
  }
  // 重建后还原填写中的表单（行仍展开且动作仍合法）
  if (state._openForm) {
    const cur = state.orders.find(x => x.orderId === state._openForm.orderId);
    const permSet = new Set((state.user && state.user.permissions) || []);
    const stillAllowed = cur && state.expandedOrder === state._openForm.orderId &&
      (TRANSITIONS[cur.status] || []).some(a => a === state._openForm.action &&
        (permSet.has("ADMIN_ALL") || permSet.has(ACTION_META[a].perm)));
    if (stillAllowed) {
      const keep = state._openForm.values;
      showOrderForm(state._openForm.orderId, state._openForm.action).then(() => {
        for (const [fid, v] of Object.entries(keep || {})) {
          const el = document.getElementById(fid);
          if (el) el.value = v;
        }
      });
    } else {
      state._openForm = null;
    }
  }
}

function toggleOrder(orderId){
  state.expandedOrder = state.expandedOrder === orderId ? null : orderId;
  renderOrders();
}

function orderTimelineHtml(o){
  const flow = [
    {z:"待确认", s:["PENDING_CONFIRMATION"]},
    {z:"待派单", s:["PENDING_ASSIGNMENT","PENDING_ACCEPTANCE"]},
    {z:"维修中", s:["PENDING_MAINTENANCE","MAINTAINING","WAITING_PARTS"]},
    {z:"待验收", s:["PENDING_INSPECTION"]},
    {z:"已完成", s:["COMPLETED"]},
  ];
  const cancelled = o.status === "CANCELLED";
  const idx = flow.findIndex(g => g.s.includes(o.status));
  let html = '<div class="timeline">';
  flow.forEach((g, i) => {
    let cls = "";
    if (i < idx) cls = "done";
    else if (i === idx) cls = o.status === "COMPLETED" ? "done" : "active";
    html += `<div class="timeline-node ${cls}">${g.z}</div>`;
  });
  if (cancelled) {
    html += `<div class="timeline-node active cancelled">已取消</div>`;
  }
  html += '</div>';
  return html;
}

function orderPanelRow(o){
  const tr = document.createElement("tr");
  tr.className = "expand";
  const conclusion = o.conclusion;
  const permSet = new Set((state.user && state.user.permissions) || []);
  const allowed = (TRANSITIONS[o.status] || []).filter(a =>
    permSet.has("ADMIN_ALL") || permSet.has(ACTION_META[a].perm));
  let html = `<td colspan="7"><div>`;
  html += orderTimelineHtml(o);
  html += `<div class="mini">标题：${esc(o.title || "--")} · 描述：${esc(o.description || "--")}` +
      ` · 负责人：${esc(o.assigneeId || "未指派")}</div>`;
  if (conclusion) {
    html += `<div class="mini">维修结论：${esc(conclusion.rootCause || "--")} / ${esc(conclusion.measures || "--")}` +
        ` · 结果 ${esc(conclusion.result || "--")} · 有效 ${esc(conclusion.effective)}</div>`;
  }
  if (o.warningId) {
    html += `<div id="wdetail-${esc(o.orderId)}" class="mini" style="margin-top:7px">关联预警详情：加载中…</div>`;
  }
  html += `<div class="ops">`;
  if (!allowed.length) {
    html += `<span class="mini">${o.status === "COMPLETED" ? "工单已完成归档" :
        o.status === "CANCELLED" ? "工单已取消" :
        "当前登录角色在此状态下无可用操作"}</span>`;
  }
  for (const a of allowed) {
    const meta = ACTION_META[a];
    // P2-7：按钮走 data-* + 事件委托，orderId 不再拼进 onclick 字符串
    html += `<button class="btn btn-${meta.kind}" style="padding:7px 14px;font-size:13px" ` +
        `data-order="${esc(o.orderId)}" data-act="${esc(a)}">${meta.label}</button>`;
  }
  html += `</div>`;
  // 操作表单（ASSIGN / SUBMIT / PASS / REJECT / CANCEL）
  const forms = allowed.filter(a => ACTION_META[a].form);
  if (forms.length) {
    html += `<div id="opform-${esc(o.orderId)}" class="opform" style="display:none"></div>`;
  }
  html += `</div></td>`;
  tr.innerHTML = html;
  // 保存展开工单的当前快照，供表单提交取 expectedVersion
  state._expandedSnapshot = Object.assign({}, o);
  if (o.warningId) loadWarningDetail(o.orderId, o.warningId);
  return tr;
}

async function loadWarningDetail(orderId, warningId){
  const box = $("wdetail-" + orderId);
  if (!box || !warningId) return;
  try {
    const w = await api("b", "/api/v1/warnings/" + encodeURIComponent(warningId),
        {headers: authHeaders()});
    if (w && w.warningId) {
      const statusZh = WARN_STATUS_ZH[w.status] || w.status;   // P2-9
      box.innerHTML =
        `<div style="margin-bottom:2px">关联预警 <span class="risk r-${esc(w.riskLevel)}">${esc(w.riskLevel)}</span> ` +
        `<b>${esc(w.warningId)}</b> <span class="mini">${esc((w.warningAt||"").replace("T"," ").replace("Z",""))}</span></div>` +
        `<div class="w-fault">${esc(w.suspectedFault)}</div>` +
        `<div class="w-meta">健康度 ${esc(w.healthScore)} · 状态 ${esc(statusZh)} · 建议：${esc(w.recommendedAction)}</div>`;
    }
  } catch (e) {
    const denied = /缺少权限|PERMISSION_DENIED/i.test(e.message || "");
    box.innerHTML = denied
      ? `<span class="mini">预警明细需 WARNING_READ 权限，当前角色不可见</span>`
      : `<span style="color:var(--red)">预警详情加载失败：${esc(e.message)}</span>`;
  }
}

async function showOrderForm(orderId, action){
  const box = $("opform-" + orderId);
  if (!box) return;
  let html = "";
  const btnAttrs = (act, label, cls) =>
    `<button class="btn ${cls}" style="padding:6px 14px;font-size:13px" ` +
    `data-order="${esc(orderId)}" data-act="${esc(act)}" data-form="1">${label}</button>`;
  if (action === "ASSIGN") {
    const engineers = await ensureAssignees();   // P2-4：选人来自 D 服务
    const options = engineers.map(u =>
      `<option value="${esc(u.userId)}">${esc(u.userId)} · ${esc(u.displayName)}</option>`).join("");
    html = `<span>派单给</span>` +
      `<select id="f-assignee">${options || '<option value="">（工程师列表不可用）</option>'}</select>` +
      btnAttrs("ASSIGN", "确认派单", "btn-cyan");
  } else if (action === "SUBMIT_FOR_INSPECTION") {
    // P2-5：去掉预填台词，只留示例提示，现场填写更真实
    html = `<input id="f-root" placeholder="根因（如：主轴轴承润滑不足导致振动升高）">` +
      `<input id="f-measure" placeholder="措施（如：补润滑换轴承，完成试运行）">` +
      `<select id="f-result"><option>RECOVERED</option><option>PARTIALLY_RECOVERED</option><option>NOT_RECOVERED</option></select>` +
      `<label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--txt);cursor:pointer">
         <input type="checkbox" id="f-restore-eq" checked style="width:16px;height:16px;cursor:pointer">
         验收通过后自动将设备恢复为<span style="color:var(--green);font-weight:600">正常运转</span>
       </label>` +
      btnAttrs("SUBMIT_FOR_INSPECTION", "提交验收", "btn-cyan");
  } else if (action === "PASS_INSPECTION") {
    html = `<label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--txt);cursor:pointer">` +
      `<input type="checkbox" id="f-restore-eq-pass" checked style="width:16px;height:16px;cursor:pointer">` +
      `验收通过后自动将设备恢复为<span style="color:var(--green);font-weight:600">正常运转</span>` +
      `</label>` +
      btnAttrs("PASS_INSPECTION", "确认验收通过", "btn-cyan");
  } else if (action === "REJECT_INSPECTION") {
    html = `<input id="f-comment" placeholder="驳回原因（必填，如：试运行振动超标）">` +
      btnAttrs("REJECT_INSPECTION", "确认驳回", "btn-danger");
  } else if (action === "CANCEL") {
    html = `<input id="f-comment" placeholder="取消原因（可选）">` +
      btnAttrs("CANCEL", "确认取消", "btn-ghost");
  }
  box.innerHTML = html;
  box.style.display = "flex";
  state._openForm = {orderId, action, values: {}};
}

async function orderAction(orderId, action, useForm){
  const o = state._expandedSnapshot;
  if (!o || o.orderId !== orderId) { toast("工单状态已变化，请刷新后重试", "err"); return; }
  const q = (sel) => document.querySelector(`#opform-${CSS.escape(orderId)} ${sel}`);
  const body = {action, operatorId: state.user.userId, expectedVersion: o.version};
  if (useForm) {
    if (action === "ASSIGN") {
      const assignee = q("#f-assignee");
      if (!assignee || !assignee.value) { toast("请选择派单工程师", "err"); return; }
      body.assigneeId = assignee.value;
    }
    if (action === "SUBMIT_FOR_INSPECTION") {
      const rootCause = (q("#f-root") || {}).value || "";
      const measures = (q("#f-measure") || {}).value || "";
      if (!rootCause.trim()) { toast("请填写根因", "err"); return; }
      if (!measures.trim()) { toast("请填写措施", "err"); return; }
      const restoreCheckbox = q("#f-restore-eq");
      body._restoreEquipment = restoreCheckbox ? restoreCheckbox.checked : true;
      body.conclusion = {
        rootCause: rootCause, measures: measures,
        result: (q("#f-result") || {}).value || "RECOVERED",
        effective: true, completedAt: nowIso(),
      };
    }
    if (action === "PASS_INSPECTION") {
      const restoreCheckboxPass = q("#f-restore-eq-pass");
      body._restoreEquipment = restoreCheckboxPass ? restoreCheckboxPass.checked : true;
    }
    if (action === "REJECT_INSPECTION") {
      const c = q("#f-comment");
      if (!c || !c.value.trim()) { toast("请填写驳回原因", "err"); return; }
      body.comment = c.value;
    }
    if (action === "CANCEL") {
      const c = q("#f-comment");
      if (c && c.value) body.comment = c.value;
    }
  } else if (ACTION_META[action].form) {
    showOrderForm(orderId, action);   // 先弹表单，确认后再提交
    return;
  }
  try {
    const result = await api("c", `/api/v1/work-orders/${encodeURIComponent(orderId)}/commands`, {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body,
    });
    log("工单操作", `${action} ${orderId} → ${STATUS_ZH[result.status] || result.status}（v${result.version}）`, true);
    toast(`${ACTION_META[action].label}成功：${STATUS_ZH[result.status] || result.status}`, "ok");
    if ((action === "SUBMIT_FOR_INSPECTION" || action === "PASS_INSPECTION")
        && body._restoreEquipment && o.equipmentId) {
      await recoverEquipmentAfterMaintenance(o.equipmentId);
    }
    state._openForm = null;
    await Promise.all([refreshOrders(), refreshDashboard(),
      state.openEq ? refreshEquipmentDetail() : Promise.resolve(),
      state.openEq ? loadTelemetry() : Promise.resolve()]);
  } catch (e) {
    log("工单操作", `${action} ${orderId}：${e.message}`, false);
    toast(`${ACTION_META[action].label}失败：${e.message}`, "err");
    refreshOrders();
  }
}

/* P2-7：工单区事件委托——行点击展开、按钮走 data-*，orderId 永不进字符串拼接 */
function wireOrdersEvents(){
  $("orders-body").addEventListener("click", (e) => {
    const actionBtn = e.target.closest("button[data-act]");
    if (actionBtn) {
      e.stopPropagation();
      orderAction(actionBtn.dataset.order, actionBtn.dataset.act,
                  actionBtn.dataset.form === "1");
      return;
    }
    const row = e.target.closest("tr.order-row");
    if (row) toggleOrder(row.dataset.order);
  });
}
