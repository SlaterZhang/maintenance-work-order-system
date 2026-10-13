/* ==========================================================================
   trace.js —— 全链路因果追溯（创新点 F）
   --------------------------------------------------------------------------
   从任意锚点（设备 / 预警 / 工单）进入，把整条因果链串起来：

     设备 → 传感器遥测 → 评分规则 → 健康评估 → 预警 → 工单 → 备件领用
       → 维修结论 → 知识库回写 → 审计留痕（traceId）

   设计原则：
     1. 每个节点都来自真实接口，哪一环缺失就如实标注哪一环，绝不编造；
     2. 链按业务键（equipmentId / warningId / orderId）拼接；
        traceId 由 C 服务审计日志携带，在「审计」节点按 traceId 分组呈现；
     3. 断链即终止：无预警则不渲染后续依赖预警的节点（工单/备件/结论…），
        用一条「链到此为止」的说明收尾，而不是铺一排空卡片。

   数据来源（全部只读，零后端改动）：
     state.equipment / state.warnings / state.orders     —— loadCore 共享快照
     A GET /api/v1/equipment/{id}/telemetry             —— 传感器节点
     B GET /api/v1/health-evaluations?equipmentId=      —— 评估节点
     B GET /api/v1/warnings/{id}                        —— 预警锚点兜底
     C GET /api/v1/spare-parts、/spare-requests         —— 备件节点
     C GET /api/v1/audit-logs?orderId=                  —— 审计节点（traceId）
     C GET /api/v1/work-orders/{id}                     —— 工单锚点兜底
     ragCorpus()（plan.js）                              —— 知识库回写节点
   ========================================================================== */
"use strict";

/* ---------- 锚点识别 ---------- */
const TRACE_PATTERNS = [
  { type: "equipment", re: /^EQ-\d+$/i },
  { type: "warning",   re: /^WARN-/i },
  { type: "order",     re: /^WO-/i },
];

function traceAnchorType(id){
  const s = String(id || "").trim();
  for (const p of TRACE_PATTERNS) if (p.re.test(s)) return p.type;
  return null;
}

/** 全局入口：warns / odetail 的「追溯」按钮都走这里 */
function traceFrom(id){
  const s = String(id || "").trim();
  if (!traceAnchorType(s)) { navigate("trace"); return; }
  navigate("trace/" + encodeURIComponent(s));
}

/* ---------- 跳转助手（节点上的 [查看] 按钮） ---------- */
function traceJumpEq(id, tab){
  if (tab) state.detailTab = tab;          // detail.load 会沿用该 Tab
  navigate("eq/" + id);
}
function traceJumpWarn(id){ navigate("warn/" + id); }   // warns.after 会自动弹详情
function traceJumpOrder(id){ navigate("odetail/" + id); }
function traceJump(pageId){ navigate(pageId); }

/* ---------- 链构造 ---------- */
/** 从锚点出发，双向补全出一条链。返回链对象（各节点数据 + 缺失标注 + 拉取耗时）。 */
async function buildTraceChain(anchorId){
  /* 共享快照兜底：直链进来时 state 可能还没加载 */
  if (!state.equipment.length) await loadEquipment();
  if (!state.warnings.length)  await loadWarnings();
  if (!state.orders.length)    await loadOrders();

  const type = traceAnchorType(anchorId);
  let eq = null, warn = null, order = null;

  if (type === "equipment") {
    eq = (state.equipment || []).find(e => e.equipmentId === anchorId) || null;
  } else if (type === "warning") {
    warn = (state.warnings || []).find(w => w.warningId === anchorId) || null;
    if (!warn) {                                              // 深链兜底：列表没有就拉详情
      try { warn = await api("b", "/api/v1/warnings/" + encodeURIComponent(anchorId), { headers: authHeaders() }); }
      catch (e) { /* 拉不到就按断链处理 */ }
    }
    if (warn) eq = (state.equipment || []).find(e => e.equipmentId === warn.equipmentId) || null;
  } else if (type === "order") {
    order = (state.orders || []).find(o => o.orderId === anchorId) || null;
    if (!order) {
      try { order = await api("c", "/api/v1/work-orders/" + encodeURIComponent(anchorId), { headers: authHeaders() }); }
      catch (e) { /* 同上 */ }
    }
    if (order) {
      eq = (state.equipment || []).find(e => e.equipmentId === order.equipmentId) || null;
      if (order.warningId) warn = (state.warnings || []).find(w => w.warningId === order.warningId) || null;
    }
  }

  /* 设备锚 / 预警锚：主链预警取该设备最新一条；同设备其余预警作为平行分支 */
  let otherWarnings = [];
  if (eq && !warn) {
    const ws = (state.warnings || [])
      .filter(w => w.equipmentId === eq.equipmentId)
      .sort((a, b) => String(b.warningAt || "").localeCompare(String(a.warningAt || "")));
    warn = ws[0] || null;
    otherWarnings = ws.slice(1);
  } else if (eq && warn) {
    otherWarnings = (state.warnings || []).filter(w => w.equipmentId === eq.equipmentId && w.warningId !== warn.warningId);
  }

  /* 有预警没工单：经 linkedOrderId 补；都没有时再看设备有没有独立工单 */
  if (warn && !order && warn.linkedOrderId) {
    order = (state.orders || []).find(o => o.orderId === warn.linkedOrderId) || null;
    if (!order) {
      try { order = await api("c", "/api/v1/work-orders/" + encodeURIComponent(warn.linkedOrderId), { headers: authHeaders() }); }
      catch (e) { /* 断链处理 */ }
    }
  }
  if (eq && !warn && !order) {
    order = (state.orders || []).find(o => o.equipmentId === eq.equipmentId) || null;
  }

  const eqId = eq ? eq.equipmentId : null;
  const orderId = order ? order.orderId : null;

  /* ---------- 按需并行拉取：一次 Promise.all，页面顶部如实标注耗时 ---------- */
  const t0 = performance.now();
  const errs = {};
  const fetchEvals = eqId
    ? api("b", "/api/v1/health-evaluations?equipmentId=" + encodeURIComponent(eqId) + "&pageSize=100", { headers: authHeaders() })
        .catch(e => { errs.evals = e.message; return null; })
    : Promise.resolve(null);
  const fetchTele = eqId
    ? api("a", "/api/v1/equipment/" + encodeURIComponent(eqId) + "/telemetry?pageSize=100", { headers: authHeaders() })
        .catch(e => { errs.tele = e.message; return null; })
    : Promise.resolve(null);
  const fetchParts = api("c", "/api/v1/spare-parts?pageSize=100", { headers: authHeaders() })
    .catch(e => { errs.parts = e.message; return null; });
  const fetchReqs = orderId
    ? api("c", "/api/v1/spare-requests?pageSize=100", { headers: authHeaders() })
        .catch(e => { errs.reqs = e.message; return null; })
    : Promise.resolve(null);
  const fetchAudit = orderId
    ? loadAuditLogs("&orderId=" + encodeURIComponent(orderId))
        .catch(e => { errs.audit = e.message; return null; })
    : Promise.resolve(null);

  const [evals, tele, parts, reqs, audit] = await Promise.all([fetchEvals, fetchTele, fetchParts, fetchReqs, fetchAudit]);
  const elapsed = Math.round(performance.now() - t0);

  const evalItems  = (evals && evals.items) || [];
  const teleItems  = (tele && tele.items) || [];
  const partItems  = (parts && parts.items) || [];
  const reqItems   = ((reqs && reqs.items) || []).filter(r => r.orderId === orderId);
  const auditItems = Array.isArray(audit) ? audit : ((audit && audit.items) || []);

  /* 触发本次预警的评估 + 该设备最新评估（两者可能不是同一条，都如实展示） */
  const warnId = warn ? warn.warningId : null;
  const triggerEval = warnId ? evalItems.find(e => e.warningId === warnId) || null : null;
  const latestEval = evalItems.length
    ? evalItems.reduce((m, e) => (String(e.evaluatedAt || "") > String(m.evaluatedAt || "") ? e : m), evalItems[0])
    : null;

  /* 知识库回写：ragCorpus 以 orderId 收录 COMPLETED 且有结论的工单 */
  let corpusHit = null;
  try {
    if (orderId && typeof ragCorpus === "function") corpusHit = ragCorpus().find(d => d.id === orderId) || null;
  } catch (e) { /* corpus 不可用不影响链 */ }

  return {
    anchorId, type, elapsed, errs,
    eq, warn, order, otherWarnings,
    evalItems, triggerEval, latestEval,
    teleItems, partItems, reqItems, auditItems, corpusHit,
  };
}

/* ---------- 渲染 ---------- */

/** 单节点骨架。tone: ok | warn | bad | dim | miss */
function traceNode(idx, icon, kicker, title, factsHtml, jump, tone){
  tone = tone || "";
  const btn = jump
    ? '<span class="tc-jump"><button class="btn btn-ghost btn-sm" onclick="' + jump + '">查看 →</button></span>'
    : "";
  return '<div class="tc-node ' + tone + '">'
    + '<div class="tc-idx">' + icon + '</div>'
    + '<div class="tc-card' + (tone === "miss" ? " miss" : "") + '">'
      + '<div class="tc-head">'
        + '<span class="tc-kicker">' + idx + ' · ' + kicker + '</span>'
        + '<span class="tc-title">' + title + '</span>'
        + btn
      + '</div>'
      + (factsHtml ? '<div class="tc-facts">' + factsHtml + '</div>' : "")
    + '</div>'
    + '</div>';
}

/** 断链说明：链到此后面的依赖节点全部不存在，一条说明收尾 */
function traceGapNode(idx, icon, kicker, reason){
  return traceNode(idx, icon, kicker, "链到此为止",
    '<div class="tc-fact">' + reason + "</div>", null, "miss");
}

function tcFact(label, value){
  return '<div class="tc-fact">' + label + '：<b>' + value + "</b></div>";
}

function riskTone(level){
  if (level === "CRITICAL" || level === "HIGH") return "bad";
  if (level === "MEDIUM") return "warn";
  if (level === "LOW") return "ok";
  return "dim";
}

function traceChainHtml(c){
  const eq = c.eq, warn = c.warn, order = c.order;
  const nodes = [];

  /* ① 设备 */
  if (eq) {
    nodes.push(traceNode("①", "⚙", "设备",
      h(eq.equipmentId) + " " + h(eq.name || ""),
      tcFact("类型", h(eq.equipmentType || "—"))
      + tcFact("产线", h(eq.productionLineId || "—"))
      + tcFact("状态", tag("equipmentStatus", eq.currentStatus))
      + tcFact("位置", h(eq.location || "—")),
      "traceJumpEq('" + h(eq.equipmentId) + "', 'overview')",
      eq.currentStatus === "MAINTAINING" ? "bad" : (eq.currentStatus === "RUNNING" ? "ok" : "dim")));
  } else {
    nodes.push(traceGapNode("①", "⚙", "设备", "锚点没有解析出设备（编号不存在或服务不可达）"));
    return nodes.join("");
  }

  /* ② 传感器 */
  if (c.teleItems.length) {
    const latest = c.teleItems.reduce((m, t) => (String(t.measuredAt || "") > String(m.measuredAt || "") ? t : m), c.teleItems[0]);
    const ev = c.triggerEval || c.latestEval;
    const trend = ev && ev.trendRatePerDay != null
      ? tcFact("趋势（B 拟合）", h(ev.trendMetric || "—") + " " + h(ev.trendRatePerDay) + " / 天 · " + h(ev.trendSampleCount || 0) + " 样本")
      : "";
    nodes.push(traceNode("②", "∿", "传感器 · 遥测",
      "最近 " + c.teleItems.length + " 条样本",
      tcFact("最新样点", h(latest.measuredAt || "—"))
      + tcFact("振动", h(latest.vibrationMmS) + " mm/s")
      + tcFact("温度", h(latest.temperatureC) + " ℃")
      + tcFact("电流", h(latest.currentA) + " A")
      + trend,
      "traceJumpEq('" + h(eq.equipmentId) + "', 'telemetry')",
      (ev && Number(ev.trendRatePerDay) > 0) ? "warn" : "ok"));
  } else {
    nodes.push(traceNode("②", "∿", "传感器 · 遥测",
      c.errs.tele ? "接口不可达：" + h(c.errs.tele) : "无遥测样本",
      "", null, "miss"));
  }

  /* ③ 规则 */
  const ruleSrc = c.triggerEval || c.latestEval || warn;
  nodes.push(traceNode("③", "⚖", "评分规则",
    h((ruleSrc && ruleSrc.modelVersion) || "rule-engine-1.0.0"),
    tcFact("疑似来源", h((ruleSrc && ruleSrc.suspectedFault) || "—"))
    + tcFact("建议措施", h((ruleSrc && ruleSrc.recommendedAction) || "—"))
    + '<div class="tc-fact">权重：振动 40 · 温度 25 · 电流 20 · 转速 15（<span class="mono">scoring.py</span> 常量）</div>',
    "traceJump('rules')", "dim"));

  /* ④ 评估 */
  const showEval = c.triggerEval || c.latestEval;
  if (showEval) {
    const isTrigger = c.triggerEval && c.triggerEval === showEval;
    nodes.push(traceNode("④", "♥", "健康评估" + (isTrigger ? "（触发本次预警）" : "（最新）"),
      "健康分 " + h(showEval.healthScore) + " · " + tag("riskLevel", showEval.riskLevel),
      tcFact("评估时间", h(showEval.evaluatedAt || "—"))
      + (showEval.predictedDaysToThreshold != null ? tcFact("预计触阈值", h(showEval.predictedDaysToThreshold) + " 天") : "")
      + tcFact("本设备评估数", c.evalItems.length + " 条"),
      "traceJump('health')", riskTone(showEval.riskLevel)));
  } else {
    nodes.push(traceNode("④", "♥", "健康评估", "该设备暂无评估记录", "", "traceJump('health')", "miss"));
  }

  /* ⑤ 预警（断链点一）。无预警但已有工单（人工报修建单）时跳过预警继续，否则终止 */
  if (warn) {
    nodes.push(traceNode("⑤", "⚠", "预警",
      h(warn.warningId) + " · " + tag("riskLevel", warn.riskLevel),
      tcFact("状态", tag("warningStatus", warn.status))
      + tcFact("预警时间", h(warn.warningAt || "—"))
      + tcFact("当时健康分", h(warn.healthScore))
      + (warn.linkedOrderId ? tcFact("已关联工单", '<span class="mono">' + h(warn.linkedOrderId) + "</span>") : tcFact("关联工单", "未转单")),
      "traceJumpWarn('" + h(warn.warningId) + "')", riskTone(warn.riskLevel)));
    if (c.otherWarnings.length) {
      const chips = c.otherWarnings.slice(0, 4).map(w =>
        '<button class="btn btn-ghost btn-sm" onclick="traceFrom(\'' + h(w.warningId) + '\')">' + h(w.warningId) + "</button>").join(" ");
      nodes.push('<div class="tc-branch">同设备另有 ' + c.otherWarnings.length
        + ' 条预警（切锚点追溯）：' + chips
        + (c.otherWarnings.length > 4 ? " 等" : "") + "</div>");
    }
  } else if (order) {
    nodes.push(traceNode("⑤", "⚠", "预警", "无预警记录 —— 本工单未由预警触发",
      '<div class="tc-fact">来源类型 ' + tag("workOrderSource", order.sourceType)
      + "：人工报修建单，跳过预警环节直接进入工单。</div>", null, "miss"));
  } else {
    nodes.push(traceGapNode("⑤", "⚠", "预警", "该设备没有预警记录 —— 传感与评估正常，未触发规则阈值。链到此为止。"));
    return nodes.join("");
  }

  /* ⑥ 工单（断链点二） */
  if (order) {
    nodes.push(traceNode("⑥", "☰", "维修工单",
      h(order.orderId) + " · " + tag("workOrderPriority", order.priority),
      tcFact("状态", tag("workOrderStatus", order.status))
      + tcFact("创建时间", h(order.createdAt || "—"))
      + tcFact("负责人", h(order.assigneeId || "未指派"))
      + tcFact("来源", tag("workOrderSource", order.sourceType)),
      "traceJumpOrder('" + h(order.orderId) + "')",
      order.status === "COMPLETED" ? "ok" : (order.priority === "P1" || order.priority === "P2" ? "warn" : "dim")));
  } else {
    nodes.push(traceGapNode("⑥", "☰", "维修工单", "该预警未关联工单（未转单或已取消）。链到此为止。"));
    return nodes.join("");
  }

  /* ⑦ 备件 */
  if (c.reqItems.length) {
    const facts = c.reqItems.map(r => {
      const part = c.partItems.find(p => p.sparePartId === r.sparePartId);
      const short = part && Number(part.availableQuantity) < Number(r.approvedQuantity || r.requestedQuantity);
      return '<div class="tc-fact' + (short ? " tc-short" : "") + '">'
        + h(part ? part.name : r.sparePartId) + "（<span class=\"mono\">" + h(r.sparePartId) + "</span>）"
        + "：申请 " + h(r.requestedQuantity) + " · 审批 " + h(r.approvedQuantity)
        + " · 已发 " + h(r.issuedQuantity)
        + (part ? " · 当前库存 " + h(part.availableQuantity) + (short ? " ⚠ 低于需求" : "") : "")
        + "</div>";
    }).join("");
    nodes.push(traceNode("⑦", "▣", "备件领用",
      c.reqItems.length + " 项领用申请",
      facts + (c.errs.parts ? '<div class="tc-fact">备件台账不可达：' + h(c.errs.parts) + "</div>" : ""),
      "traceJump('spares')",
      c.reqItems.some(r => {
        const part = c.partItems.find(p => p.sparePartId === r.sparePartId);
        return part && Number(part.availableQuantity) < Number(r.approvedQuantity || r.requestedQuantity);
      }) ? "warn" : "ok"));
  } else {
    nodes.push(traceNode("⑦", "▣", "备件领用", "本工单未领用备件",
      "", "traceJump('spares')", "miss"));
  }

  /* ⑧ 结论 */
  const con = order.conclusion;
  if (con && (con.rootCause || con.measures)) {
    nodes.push(traceNode("⑧", "✓", "维修结论",
      h(con.rootCause || "—") + (con.effective ? " · 措施有效" : " · 未见效标注"),
      tcFact("措施", h(con.measures || "—"))
      + tcFact("停机时长", (con.downtimeMinutes != null ? h(con.downtimeMinutes) + " 分钟" : "—"))
      + tcFact("是否有效", con.effective ? "✓ 有效" : "✗ 无效/未标注"),
      "traceJumpOrder('" + h(order.orderId) + "')",
      con.effective ? "ok" : "warn"));
  } else {
    nodes.push(traceNode("⑧", "✓", "维修结论", "工单未完结，尚无维修结论",
      "", "traceJumpOrder('" + h(order.orderId) + "')", "miss"));
  }

  /* ⑨ 知识库回写 */
  if (c.corpusHit) {
    nodes.push(traceNode("⑨", "▤", "知识库回写",
      "已收录语料（" + h(c.corpusHit.kind || "维修结论") + "）",
      tcFact("语料 ID", '<span class="mono">' + h(c.corpusHit.id) + "</span>")
      + '<div class="tc-fact">后续在「知识库助手」提问时，本条结论可被检索命中 —— 闭环回写。</div>',
      "traceJump('rag')", "ok"));
  } else {
    nodes.push(traceNode("⑨", "▤", "知识库回写", "未回写（工单未完成或无结论）",
      "", "traceJump('rag')", "miss"));
  }

  /* ⑩ 审计（traceId 在这一层呈现） */
  if (c.auditItems.length) {
    const traceIds = [...new Set(c.auditItems.map(a => a.traceId).filter(Boolean))];
    const recent = c.auditItems.slice(0, 4).map(a =>
      '<div class="tc-fact">' + h(a.createdAt || "—") + " · " + h(a.action)
      + ' <span class="mono">' + h(a.beforeValue || "—") + " → " + h(a.afterValue || "—") + "</span>"
      + " · " + h(a.operatorId) + "</div>").join("");
    nodes.push(traceNode("⑩", "◫", "审计留痕",
      c.auditItems.length + " 条留痕 · " + traceIds.length + " 个 traceId",
      (traceIds.length
        ? '<div class="tc-fact">traceId：' + traceIds.slice(0, 2).map(t => '<span class="mono">' + h(t) + "</span>").join(" · ")
          + (traceIds.length > 2 ? " 等" : "")
          + '<span class="mini">（C 服务审计携带，跨事件链路键）</span></div>'
        : "")
      + recent,
      "traceJump('audit')", "ok"));
  } else {
    nodes.push(traceNode("⑩", "◫", "审计留痕",
      c.errs.audit ? "审计接口不可达：" + h(c.errs.audit) : "该工单暂无审计记录",
      "", "traceJump('audit')", "miss"));
  }

  return nodes.join("");
}

/* ---------- 页面 ---------- */

function traceSearch(){
  const kw = (document.getElementById("trace-kw") || {}).value || "";
  if (!traceAnchorType(kw)) {
    toast("请输入设备 / 预警 / 工单编号（如 EQ-000001）", "err");
    return;
  }
  traceFrom(kw);
}

function traceSearchKey(ev){
  if (ev && ev.key === "Enter") traceSearch();
}

function traceDefaultChips(){
  const eqs = state.equipment || [];
  const target = eqs.find(e => e.equipmentId === "EQ-000001") || eqs[0];
  const warn = (state.warnings || [])[0];
  const order = (state.orders || [])[0];
  const chips = [];
  if (target) chips.push('<button class="btn btn-ghost btn-sm" onclick="traceFrom(\'' + h(target.equipmentId) + '\')">'
    + h(target.equipmentId) + "（数据最全）</button>");
  if (warn) chips.push('<button class="btn btn-ghost btn-sm" onclick="traceFrom(\'' + h(warn.warningId) + '\')">'
    + h(warn.warningId) + "（预警锚点）</button>");
  if (order) chips.push('<button class="btn btn-ghost btn-sm" onclick="traceFrom(\'' + h(order.orderId) + '\')">'
    + h(order.orderId) + "（工单锚点）</button>");
  return chips.join(" ");
}

registerPage("trace", {
  async load(ctx){
    await loadEquipment();
    if (!state.warnings.length) await loadWarnings();
    if (!state.orders.length) await loadOrders();

    const anchor = (ctx.params && ctx.params.anchor) || "EQ-000001";
    const c = await buildTraceChain(anchor);

    const head = pageHdr("全链路因果追溯", "从传感器到维修结论 · 一条链还原来龙去脉")
      + '<div class="card mt"><div class="toolbar">'
      + '<input id="trace-kw" style="flex:1;min-width:240px" placeholder="输入设备 / 预警 / 工单编号，如 EQ-000001 · WARN-2026xxxx · WO-2026xxxx"'
      + ' value="' + h(c.anchorId) + '" onkeydown="traceSearchKey(event)">'
      + '<button class="btn btn-p" onclick="traceSearch()">⛓ 追溯</button>'
      + "</div>"
      + '<div class="trace-chips">' + traceDefaultChips() + "</div>"
      + "</div>";

    let body;
    if (!c.eq && !c.warn && !c.order) {
      body = '<div class="card mt">' + emptyBox("锚点不存在", "没有找到 <span class=\"mono\">" + h(c.anchorId)
        + "</span> 对应的设备 / 预警 / 工单。可核对编号后重试，或用上方快捷锚点。") + "</div>";
    } else {
      body =
        '<div class="card mt">'
        + '<div class="trace-meta">追溯锚点：<b>' + h(c.anchorId) + "</b> · 类型 " + h(c.type)
        + " · 并行拉取 5 个只读接口 · 耗时 " + h(c.elapsed) + "ms</div>"
        + '<div class="trace-chain">' + traceChainHtml(c) + "</div>"
        + noticeLive("数据来源：A <span class=\"mono\">GET /equipment/{id}/telemetry</span>；"
          + "B <span class=\"mono\">GET /health-evaluations?equipmentId=</span>；"
          + "C <span class=\"mono\">GET /spare-parts · /spare-requests · /audit-logs?orderId=</span>。"
          + "链按业务键拼接，traceId 由 C 审计日志携带；断链如实标注，不编造节点。")
        + "</div>";
    }

    return head + body;
  },

  after(){
    const input = document.getElementById("trace-kw");
    if (input) input.focus();
  },
});
