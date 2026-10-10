/* ============================================================================
 * 页面：备件领用申请（#/sreq）
 * 数据来源：C GET /api/v1/spare-requests（支持 status / orderId / sparePartId /
 *          requesterId 过滤）
 * 命令入口：C POST /api/v1/spare-requests/{requestId}/commands
 * 状态机权威：apps/maintenance/src/domain/state_machine.py 的 SPARE_TRANSITIONS
 *           与 SPARE_ACTION_PERMISSION
 * ==========================================================================*/

// 状态 → 可执行动作（照抄 SPARE_TRANSITIONS，不要凭印象改）
const SREQ_TRANSITIONS = {
  PENDING_APPROVAL: ["APPROVE", "REJECT", "CANCEL"],
  APPROVED: ["RESERVE", "CANCEL"],
  RESERVED: ["ISSUE", "CANCEL"],
  ISSUED: ["RETURN", "CLOSE"],
  PARTIALLY_RETURNED: ["RETURN", "CLOSE"],
  CLOSED: [], REJECTED: [], CANCELLED: [],
};
// 动作 → 权限码（照抄 SPARE_ACTION_PERMISSION）
const SREQ_ACTION_PERM = {
  APPROVE:"SPARE_APPROVE", REJECT:"SPARE_APPROVE", RESERVE:"SPARE_APPROVE",
  CANCEL:"SPARE_APPROVE", ISSUE:"SPARE_ISSUE", RETURN:"SPARE_ISSUE", CLOSE:"SPARE_ISSUE",
};
// 动作 → 中文（发料/退料/关单在界面上要写清方向，避免"操作"两字糊过去）
const SREQ_ACTION_ZH = {
  APPROVE:"批准", REJECT:"驳回", RESERVE:"预留库存",
  ISSUE:"发料", RETURN:"退料", CLOSE:"关单", CANCEL:"取消申请",
};
// 需要弹窗补充信息的动作
const SREQ_FORM_ACTIONS = { APPROVE:"approve", ISSUE:"issue", RETURN:"return", REJECT:"reject", CANCEL:"cancel" };

function sreqAllowed(r){
  const all = SREQ_TRANSITIONS[r.status] || [];
  if (hasPerm("ADMIN_ALL")) return all.slice();
  return all.filter(a => hasPerm(SREQ_ACTION_PERM[a]));
}

function sreqTableHtml(){
  const f = state.sreqFilter || {};
  let list = state.sreqRequests || [];
  if (f.status) list = list.filter(r => r.status === f.status);
  if (f.kw) {
    const k = f.kw.toLowerCase();
    list = list.filter(r => [r.requestId, r.orderId, r.sparePartId, r.requesterId]
      .some(v => String(v || "").toLowerCase().includes(k)));
  }

  const rows = list.map(r => {
    const acts = sreqAllowed(r);
    const btns = acts.length
      ? acts.map(a => '<button class="btn btn-o btn-sm" style="margin-right:4px" onclick="openSreqAction(\''
          + h(r.requestId) + '\',\'' + a + '\')">' + h(SREQ_ACTION_ZH[a]) + '</button>').join("")
      : '<span class="mini">—</span>';
    return [
      '<span class="mono">' + h(r.requestId) + '</span>',
      '<span class="mono">' + h(r.orderId || "—") + '</span>',
      h(spareName(r.sparePartId)),
      h(r.requestedQuantity) + ' ' + h(spareUnit(r.sparePartId)),
      h(r.approvedQuantity != null ? r.approvedQuantity : "—"),
      h(r.issuedQuantity != null ? r.issuedQuantity : "—"),
      h(r.returnedQuantity != null ? r.returnedQuantity : "—"),
      tag("spareRequestStatus", r.status),
      h(r.requesterId || "—"),
      '<span class="mini">' + fmtTime(r.createdAt) + '</span>',
      btns,
    ];
  });

  return '<div id="sreq-tbl">'
    + table(["申请号", "工单", "备件", "申请量", "批准量", "已发", "已退", "状态",
             "申请人", "创建时间", "操作"], rows,
        { emptyText: "暂无备件申请", emptyHint: "备件申请必须挂在工单下——请到工单详情页发起，或点右上「＋ 新建申请」" })
    + '</div>';
}

function applySreqFilter(){
  const f = {
    status: (document.getElementById("sq-status") || {}).value || "",
    kw: ((document.getElementById("sq-kw") || {}).value || "").trim(),
  };
  state.sreqFilter = f;
  return route(true);
}

function resetSreqFilter(){ state.sreqFilter = null; return route(true); }

function sreqBody(){
  const f = state.sreqFilter || {};
  const list = state.sreqRequests || [];
  const byS = s => list.filter(r => r.status === s).length;
  const pending = byS("PENDING_APPROVAL");
  const reserved = byS("RESERVED");
  const issued = byS("ISSUED") + byS("PARTIALLY_RETURNED");

  let html = pageHdr("备件领用申请", "申请 · 审批 · 发料 · 退料闭环",
    '<div class="btn-group">'
    + '<button class="btn btn-o btn-sm" onclick="exportSreqCsv()">⇩ 导出 CSV</button>'
    + '<button class="btn btn-p btn-sm" onclick="openCreateSpareRequestModal()">＋ 新建申请</button>'
    + '</div>');

  html += noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/spare-requests</span>、"
    + "<span class=\"mono\">POST /api/v1/spare-requests/{requestId}/commands</span>（均已实现）。"
    + "库存不做覆盖式写：申请只登记，预留才占用，发料才真正扣减，退料回冲——每一步都有流水可对账。");

  html += '<div class="grid g5 mt">'
    + kpi(pending ? "yellow" : "green", "待审批", pending, pending ? "等待主管批准" : "无积压")
    + kpi("cyan",  "已预留", reserved, "占库存未出库")
    + kpi("purple", "已发料", issued, "含部分退料")
    + kpi(byS("REJECTED") ? "red" : "dim", "已驳回", byS("REJECTED"), "终态")
    + kpi("dim",   "申请总数", list.length, "全部历史")
    + '</div>';

  html += '<div class="card mt"><div class="toolbar">'
    + '<input id="sq-kw" placeholder="申请号 / 工单 / 备件 / 申请人" style="width:230px" value="' + h(f.kw || "") + '">'
    + '<select id="sq-status"><option value="">全部状态</option>'
      + ["PENDING_APPROVAL","APPROVED","RESERVED","ISSUED","PARTIALLY_RETURNED",
         "CLOSED","REJECTED","CANCELLED"]
          .map(s => '<option value="' + s + '"' + (f.status === s ? " selected" : "") + '>'
            + h(enumZh("spareRequestStatus", s, s)) + '</option>').join("")
    + '</select>'
    + '<button class="btn btn-o btn-sm" onclick="applySreqFilter()">查询</button>'
    + '<button class="btn btn-o btn-sm" onclick="resetSreqFilter()">重置</button>'
    + '<span class="mini" style="margin-left:auto">共 ' + list.length + ' 条</span>'
    + '</div>'
    + sreqTableHtml()
    + '</div>';

  // 权限边界说明：三个权限码分离，是本模块最重要的治理设计
  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("领用状态机", "8 态 / 7 动作")
    + table(["状态", "可执行动作", "权限码"], [
        ["PENDING_APPROVAL", "APPROVE / REJECT / CANCEL", "SPARE_APPROVE"],
        ["APPROVED", "RESERVE / CANCEL", "SPARE_APPROVE"],
        ["RESERVED", "ISSUE / CANCEL", "SPARE_ISSUE（取消用 SPARE_APPROVE）"],
        ["ISSUED", "RETURN / CLOSE", "SPARE_ISSUE"],
        ["PARTIALLY_RETURNED", "RETURN / CLOSE", "SPARE_ISSUE"],
        ["CLOSED / REJECTED / CANCELLED", "—（终态）", "—"],
      ].map(r => ['<span class="mono mini">' + r[0] + '</span><br>'
                    + (r[0].includes("/") ? "" : tag("spareRequestStatus", r[0])),
                  '<span class="mini mono">' + r[1] + '</span>',
                  '<span class="mini mono">' + r[2] + '</span>']))
    + '<div class="mini mt">当前角色权限：'
      + ([...permSet()].length
          ? [...permSet()].map(p => '<span class="mono">' + h(p) + '</span>').join("、")
          : '<span style="color:var(--yellow)">未能读取（D 服务不可达或未登录）</span>')
      + '</div>'
    + '</div>'
    + '<div class="card">' + sect("为什么三方分离", "治理设计")
    + '<div class="timeline">'
    + '<div class="tl ok"><div class="tt">申请人不等于审批人</div><div class="td">'
      + '维修工程师提交申请（<code>SPARE_REQUEST</code>），但批准要 <code>SPARE_APPROVE</code>——'
      + '维修主管才有。避免"自己要料自己批"。</div></div>'
    + '<div class="tl ok"><div class="tt">审批人不等于发料人</div><div class="td">'
      + '批准与预留是账面上的（<code>SPARE_APPROVE</code>），真正出库是 <code>SPARE_ISSUE</code>——'
      + '仓库管理员的权限。账面与实物分开，责任才落得下去。</div></div>'
    + '<div class="tl warn"><div class="tt">预留 ≠ 出库</div><div class="td">'
      + '<code>RESERVE</code> 只把可用量转成预留量（在库量不变），<code>ISSUE</code> 才真正扣在库量。'
      + '如果两个概念混在一起，就会出现"审批了但东西还在库里，别人又领走了"。</div></div>'
    + '<div class="tl ok"><div class="tt">退料回冲而非覆盖</div><div class="td">'
      + '退料写 <code>PARTIALLY_RETURNED</code> 并累加 <code>returnedQuantity</code>，'
      + '库存加回，但申请单不会消失——原始领用记录保留，便于事后对账与责任追溯。</div></div>'
    + '</div></div></div>';

  return html;
}

function exportSreqCsv(){
  downloadCsv("spare-requests", ["申请号", "工单", "备件", "申请量", "批准量", "已发", "已退",
    "状态", "申请人", "审批人", "事由", "创建时间", "版本"],
    (state.sreqRequests || []).map(r => [r.requestId, r.orderId, r.sparePartId,
      r.requestedQuantity, r.approvedQuantity, r.issuedQuantity, r.returnedQuantity,
      enumZh("spareRequestStatus", r.status, r.status), r.requesterId, r.approverId || "",
      r.reason || "", r.createdAt, r.version]));
}

/** 执行备件申请动作。quantity 仅 APPROVE/ISSUE/RETURN 需要 */
async function runSreqAction(requestId, action, quantity){
  const r = (state.sreqRequests || []).find(x => x.requestId === requestId);
  if (!r) { toast("申请不存在", "err"); return; }
  const body = {
    action: action,
    operatorId: (state.user && state.user.userId) || "",
    expectedVersion: r.version,
  };
  if (quantity != null && quantity !== "") body.quantity = parseInt(quantity, 10);
  try {
    const out = await api("c", "/api/v1/spare-requests/" + encodeURIComponent(requestId) + "/commands", {
      method: "POST",
      headers: Object.assign(authHeaders(), { "Idempotency-Key": uuidv4() }),
      body: body,
    });
    closeModal();
    log("备件" + (SREQ_ACTION_ZH[action] || action),
      requestId + " → " + enumZh("spareRequestStatus", out.status, out.status), true);
    toast("已" + (SREQ_ACTION_ZH[action] || action) + "：" + requestId, "ok");
    await loadSpareRequests();
    await loadSpareParts();     // 预留/发料/退料都改库存，刷新水位
    await route(true);
  } catch (e) {
    log("备件" + (SREQ_ACTION_ZH[action] || action), e.message, false);
    toast("操作失败：" + e.message, "err");
  }
}

function openSreqAction(requestId, action){
  const r = (state.sreqRequests || []).find(x => x.requestId === requestId);
  if (!r) return;
  const zh = SREQ_ACTION_ZH[action] || action;
  const kind = SREQ_FORM_ACTIONS[action];

  // 无表单动作直接执行（RESERVE / CLOSE）
  if (!kind) { runSreqAction(requestId, action); return; }

  let fields = '';
  if (action === "APPROVE") {
    fields = '<div class="field"><div class="mini">批准数量 *（申请 ' + h(r.requestedQuantity)
      + '，库存可用 ' + h((sparePartOf(r.sparePartId) || {}).availableQuantity) + '）</div>'
      + '<input id="sq-qty" class="inp" type="number" min="1" value="' + h(r.requestedQuantity)
      + '" style="width:100%"></div>';
  } else if (action === "ISSUE") {
    fields = '<div class="field"><div class="mini">实发数量 *（批准 ' + h(r.approvedQuantity) + '）</div>'
      + '<input id="sq-qty" class="inp" type="number" min="1" value="'
      + h(r.approvedQuantity || r.requestedQuantity) + '" style="width:100%"></div>';
  } else if (action === "RETURN") {
    const maxRet = (r.issuedQuantity || 0) - (r.returnedQuantity || 0);
    fields = '<div class="field"><div class="mini">退料数量 *（已发 ' + h(r.issuedQuantity)
      + '，最多可退 ' + h(maxRet) + '）</div>'
      + '<input id="sq-qty" class="inp" type="number" min="1" max="' + h(maxRet)
      + '" value="' + h(maxRet) + '" style="width:100%"></div>';
  } else {
    fields = '<div class="field"><div class="mini">原因 *</div>'
      + '<input id="sq-reason" class="inp" style="width:100%" placeholder="'
      + (action === "REJECT" ? "如：库存不足，先保 P1 工单" : "如：工单取消，不再需要")
      + '"></div>';
  }

  openModal(zh + " · " + requestId, fields
    + '<div class="mini mt" style="line-height:1.7">'
    + '操作人由服务端从 JWT 覆写，命令体里的 operatorId 不可信；'
    + '命令带 <span class="mono">Idempotency-Key</span>，重复提交不会重复扣库存。</div>',
    { width: 480,
      footer: '<button class="btn btn-ghost" onclick="closeModal()">取消</button>'
        + '<button class="btn" onclick="submitSreqAction(\'' + h(requestId) + '\',\'' + action + '\')">确认'
        + h(zh) + '</button>' });
}

async function submitSreqAction(requestId, action){
  const kind = SREQ_FORM_ACTIONS[action];
  let qty = null, reason = null;
  if (kind === "approve" || kind === "issue" || kind === "return") {
    qty = (document.getElementById("sq-qty") || {}).value;
    if (!qty || parseInt(qty, 10) < 1) { toast("数量必须大于 0", "err"); return; }
  } else {
    reason = ((document.getElementById("sq-reason") || {}).value || "").trim();
    if (!reason) { toast("请填写原因", "err"); return; }
  }
  if (reason) { await runSreqActionWithComment(requestId, action, reason); return; }
  await runSreqAction(requestId, action, qty);
}

/** REJECT / CANCEL 带不了 quantity，把原因塞进 comment（契约允许可选 comment） */
async function runSreqActionWithComment(requestId, action, comment){
  const r = (state.sreqRequests || []).find(x => x.requestId === requestId);
  if (!r) return;
  try {
    const out = await api("c", "/api/v1/spare-requests/" + encodeURIComponent(requestId) + "/commands", {
      method: "POST",
      headers: Object.assign(authHeaders(), { "Idempotency-Key": uuidv4() }),
      body: {
        action: action,
        operatorId: (state.user && state.user.userId) || "",
        expectedVersion: r.version,
        comment: comment,
      },
    });
    closeModal();
    log("备件" + (SREQ_ACTION_ZH[action] || action), requestId + " · " + comment, true);
    toast("已" + (SREQ_ACTION_ZH[action] || action) + "：" + requestId, "ok");
    await loadSpareRequests();
    await loadSpareParts();
    await route(true);
  } catch (e) {
    log("备件" + (SREQ_ACTION_ZH[action] || action), e.message, false);
    toast("操作失败：" + e.message, "err");
  }
}

registerPage("sreq", {
  async load(ctx){
    if (!state.spareParts.length) await loadSpareParts();
    state.sreqRequests = await loadSpareRequests();
    return sreqBody();
  },
  async poll(ctx){
    if (!document.getElementById("sreq-tbl")) return;
    state.sreqRequests = await loadSpareRequests();
    const el = document.getElementById("sreq-tbl");
    if (el) el.outerHTML = sreqTableHtml();
  },
});
