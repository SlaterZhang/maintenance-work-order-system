/* 设备详情 —— 6 个 Tab：概览 / 遥测趋势 / 健康评估 / 预警记录 / 维修工单 / 设备档案
   复用既有的设备详情逻辑（equipment.js 的 refreshEquipmentDetail / loadTelemetry）
   与注入工作台（inject.js），在框架内以真实接口驱动。 */
"use strict";

const DETAIL_TABS = ["overview", "telemetry", "health", "warns", "orders", "profile"];
const DETAIL_TAB_ZH = {
  overview:"概览", telemetry:"遥测趋势", health:"健康评估",
  warns:"预警记录", orders:"维修工单", profile:"设备档案",
};

registerPage("detail", {
  async load(ctx){
    const eqId = ctx.params.equipmentId;
    if (!eqId) return pageHdr("设备详情") + emptyBox("缺少设备编号", "请从设备台账点击设备进入");

    state.openEq = eqId;
    state.detailTab = state.detailTab || "overview";

    // 共享快照不足时补齐
    if (!state.equipment.length) await loadEquipment();
    await loadCore();
    await loadDetailExtras(eqId);

    return detailHtml(eqId);
  },

  after(ctx){
    const eqId = ctx.params.equipmentId;
    if (!eqId) return;
    // 概览与遥测两个 Tab 才需要图表；切到其它 Tab 时容器不存在，跳过
    if (state.detailTab === "telemetry" || state.detailTab === "overview") {
      state.chartData = []; state.telemetrySeen = new Set();
      state.charts = {}; state.chartOk = false;
      if (document.getElementById("chart-temp")) loadTelemetry(true);
    }
    if (typeof refreshEquipmentDetail === "function") refreshEquipmentDetail();
    if (typeof updateWorkbenchButtons === "function") updateWorkbenchButtons();
  },

  async poll(ctx){
    const eqId = ctx.params.equipmentId;
    if (!eqId || !document.getElementById("eq-status")) return;
    if (typeof refreshEquipmentDetail === "function") await refreshEquipmentDetail();
    if (state.detailTab === "telemetry" && document.getElementById("chart-temp")) {
      await loadTelemetry(false);
    }
  },
});

/** 详情页专属数据：遥测快照 + 该设备的预警/评估历史 */
async function loadDetailExtras(eqId){
  state.detailTelemetry = [];
  try {
    const d = await api("a", "/api/v1/equipment/" + encodeURIComponent(eqId)
      + "/telemetry?pageSize=30", { headers: authHeaders() });
    state.detailTelemetry = (d.items || []).slice().reverse();
  } catch (e) { /* 图表与快照可降级 */ }

  state.detailEvaluations = await loadEvaluations("&equipmentId=" + encodeURIComponent(eqId));
  state.detailWarnings = (state.warnings || []).filter(w => w.equipmentId === eqId);
  state.detailOrders = (state.orders || []).filter(o => o.equipmentId === eqId);
}

function detailHtml(eqId){
  const eq = (state.equipment || []).find(e => e.equipmentId === eqId);
  if (!eq) {
    return pageHdr("设备详情 · " + h(eqId))
      + noticeWarn("设备 " + h(eqId) + " 不存在或已被移出主数据。")
      + emptyBox("未找到该设备", "A 服务 GET /api/v1/equipment/" + h(eqId) + " 返回 404")
      + '<div class="mt"><button class="btn" onclick="navigate(\'assets\')">← 返回设备台账</button></div>';
  }

  const hp = state.healthMap[eqId];
  const ev = state.latestEvaluation[eqId];
  const score = hp ? Number(hp.score) : null;
  const lastSample = state.detailTelemetry.length
    ? state.detailTelemetry[state.detailTelemetry.length - 1] : null;

  let html = pageHdr("设备详情 · " + h(eq.equipmentId), h(eq.name || "") + " · "
      + h(eq.productionLineId || "—") + " · " + h(eq.location || ""),
    '<button class="btn btn-ghost btn-sm" onclick="refreshCurrent()">↻ 刷新</button>'
    + '<button class="btn btn-g btn-sm" onclick="recoverFromDetail()">☑ 恢复正常数据</button>'
    + '<button class="btn btn-p btn-sm" onclick="navigate(\'orders\')">+ 派工单</button>');

  html += noticeLive("数据来源：真实接口 — A <span class=\"mono\">GET /api/v1/equipment/{id}</span>、"
    + "<span class=\"mono\">/telemetry</span>、<span class=\"mono\">POST .../simulate</span>（注入）、"
    + "<span class=\"mono\">POST .../enabled</span>（停用/启用）；B <span class=\"mono\">GET /warnings</span>、"
    + "<span class=\"mono\">/health-evaluations</span>；C <span class=\"mono\">GET /work-orders</span>。");

  // ---- 四张关键指标卡 ----
  html += '<div class="grid g4 mt">';
  html += '<div class="card"><div class="mini">运行状态</div>'
    + '<div id="eq-status" style="font-size:26px;font-weight:700;margin:6px 0">'
    + enumZh("equipmentStatus", eq.currentStatus) + '</div>'
    + '<div class="mini mono">v' + h(eq.version) + (eq.enabled === false ? " · 已停用" : " · 已启用") + '</div></div>';
  html += '<div class="card"><div class="mini">健康度</div>'
    + '<div id="eq-health" style="font-size:26px;font-weight:700;margin:6px 0;color:'
    + (score === null ? "var(--dim)" : toneColor(score >= 80 ? "ok" : score >= 60 ? "warn" : "bad")) + '">'
    + (score === null ? "—" : fmtNum(score, 1)) + '</div>'
    + '<div class="mini">风险等级 ' + (hp ? tag("riskLevel", hp.riskLevel) : "—") + '</div></div>';
  html += '<div class="card"><div class="mini">振动 mm·s⁻¹</div>'
    + '<div style="font-size:26px;font-weight:700;margin:6px 0">'
    + (lastSample ? fmtMetric(lastSample.vibrationMmS, 2) : "—") + '</div>'
    + '<div class="mini">正常 &lt;3 · 满扣 6</div></div>';
  html += '<div class="card"><div class="mini">温度 ℃</div>'
    + '<div style="font-size:26px;font-weight:700;margin:6px 0">'
    + (lastSample ? fmtMetric(lastSample.temperatureC, 1) : "—") + '</div>'
    + '<div class="mini">正常 &lt;70 · 满扣 90</div></div>';
  html += '</div>';

  // ---- Tab 条 ----
  html += '<div class="card mt"><div class="tabs">'
    + DETAIL_TABS.map(t => '<button class="' + (state.detailTab === t ? "on" : "")
        + '" onclick="detailTab(\'' + t + '\')">' + DETAIL_TAB_ZH[t] + '</button>').join("")
    + '</div></div>';

  html += '<div class="mt">' + detailTabHtml(eq, ev) + '</div>';
  return html;
}

function detailTabHtml(eq, ev){
  const eqId = eq.equipmentId;
  switch (state.detailTab) {
    case "telemetry": return detailTelemetryHtml();
    case "health":    return detailHealthHtml(ev);
    case "warns":     return detailWarnsHtml(eqId);
    case "orders":    return detailOrdersHtml(eqId);
    case "profile":   return detailProfileHtml(eq);
    default:          return detailOverviewHtml(eq, ev);
  }
}

/* ---------- Tab 1：概览（最近一次评估 + 扣分明细 + 注入工作台） ---------- */
function detailOverviewHtml(eq, ev){
  let html = '<div class="grid g-2-1">';

  html += '<div class="card">' + sect("最近一次健康评估", "B 服务");
  if (!ev) {
    html += emptyBox("还没有健康评估记录",
      "在下方「模拟数据注入工作台」注入一次异常或正常数据，A 会调用 B 完成评分");
  } else {
    html += '<div class="tbl-wrap"><table><tbody>'
      + row2("评估编号", '<span class="mono">' + h(ev.evaluationId || "—") + '</span>')
      + row2("健康分", '<span class="mono" style="font-size:16px;color:'
          + toneColor(Number(ev.healthScore) >= 80 ? "ok" : Number(ev.healthScore) >= 60 ? "warn" : "bad")
          + '">' + fmtNum(ev.healthScore, 1) + ' / 100</span>')
      + row2("风险等级", tag("riskLevel", ev.riskLevel))
      + row2("疑似故障", h(ev.suspectedFault || "—"))
      + row2("评分模型", '<span class="mono">' + h(ev.modelVersion || "—") + '</span>')
      + row2("趋势外推", h(trendConclusionZh(ev) || "样本不足或趋势平稳"))
      + row2("建议措施", h(ev.recommendedAction || "—"))
      + row2("评估时间", '<span class="mono">' + fmtTimeSec(ev.evaluatedAt) + '</span>')
      + '</tbody></table></div>';
  }
  html += '</div>';

  // 评分口径参照表（静态：权重与阈值定义在 B 的 scoring.py，属可核对的口径而非本机数据）
  html += '<div class="card">' + sect("评分口径", "与 B scoring.py 一致")
    + noticeInfo("健康分从 100 起扣：<span class=\"mono\">ratio = (value − normal) / (full − normal)</span>，"
      + "<span class=\"mono\">score = 100 − Σ(weight × clamp(ratio, 0, 1))</span>。"
      + "任一指标进入报警区（ratio ≥ 1）健康分不高于 59.9，进入跳闸区（ratio ≥ 1.5）不高于 39.9——"
      + "<b>避免单项严重异常被加权平均稀释</b>。")
    + '<div class="tbl-wrap"><table><thead><tr><th>指标</th><th>单位</th><th>正常</th>'
    + '<th>满扣</th><th>权重</th><th>疑似故障来源</th></tr></thead><tbody>'
    + SCORE_METRICS.map(function (m) {
        return '<tr><td>' + m.zh + '</td><td class="mini mono">' + m.unit + '</td>'
          + '<td class="mono">' + m.normal + '</td><td class="mono">' + m.full + '</td>'
          + '<td class="mono">' + m.weight + '</td>'
          + '<td class="mini">' + m.fault + '</td></tr>';
      }).join("")
    + '</tbody></table></div>'
    + '<div class="mini" style="margin-top:8px;line-height:1.7">'
    + '阈值参考 ISO 20816-1:2016（前身 ISO 10816）振动烈度分区，取更保守的 3.0 / 6.0 mm·s⁻¹ 作教学演示阈值。'
    + '转速按相对额定 1500 rpm 的偏离比例衡量（5% 正常 / 15% 满扣）。</div>'
    + '</div></div>';

  // ---- 注入工作台（沿用 inject.js） ----
  html += '<div class="card mt">' + sect("模拟数据注入工作台", "第十章演示剧本")
    + '<div class="li" style="gap:10px;flex-wrap:wrap">'
    + '<button id="btn-abnormal" class="btn btn-danger" onclick="injectData(\'abnormal\')">⚡ 注入异常数据</button>'
    + '<button id="btn-normal" class="btn btn-green" onclick="injectData(\'normal\')">☑ 注入正常数据</button>'
    + '<button id="btn-toggle-enabled" class="btn" onclick="toggleEquipmentEnabled()">⛔ 停用设备</button>'
    + '</div>'
    + '<div id="inject-hint" class="mini" style="margin-top:8px;line-height:1.7">'
    + '注入异常（96.7℃ / 9.8 mm·s⁻¹ / 18.3 A）会走通 A 写入 → B 评分建预警 → C 自动建单 → D 通知 全链路；'
    + '注入正常（65.2℃ / 3.4 mm·s⁻¹）会复位设备状态并自动闭环活跃预警。</div>'
    + '<div class="console mt"><div id="log" class="mini mono"></div></div>'
    + '</div>';
  return html;
}

function detailTelemetryHtml(){
  const rows = (state.detailTelemetry || []).slice().reverse();
  let html = '<div class="card">' + sect("遥测趋势", "最近 30 个样点 · A 服务")
    + noticeInfo("阈值线口径与 B 规则引擎一致（<span class=\"mono\">scoring.py</span>）："
      + "温度 70/90℃、振动 3/6 mm·s⁻¹、电流 15/30 A。虚线为按最近斜率外推 12 小时的趋势线——"
      + "<b>上行量不足满扣阈值 3% 时判定为平稳，不画外推线</b>，避免用噪声画出误导性预测。");

  if (!rows.length) {
    html += emptyBox("暂无遥测数据", "注入一次数据后即可看到趋势");
    html += '</div>';
    return html;
  }

  html += '<div class="grid g3 mt">'
    + '<div class="chartbox"><div class="mini">温度 ℃</div><div id="chart-temp" class="chart"></div></div>'
    + '<div class="chartbox"><div class="mini">振动 mm·s⁻¹</div><div id="chart-vib" class="chart"></div></div>'
    + '<div class="chartbox"><div class="mini">电流 A</div><div id="chart-curr" class="chart"></div></div>'
    + '</div></div>';

  html += '<div class="card mt">' + sect("原始样点", "最近 " + Math.min(rows.length, 30) + " 条")
    + '<div class="tbl-wrap"><table><thead><tr><th>时间</th><th>温度 ℃</th><th>振动 mm·s⁻¹</th>'
    + '<th>电流 A</th><th>转速 rpm</th><th>样点 ID</th></tr></thead><tbody>'
    + rows.slice(0, 30).map(s => '<tr>'
        + '<td class="mono mini">' + fmtTimeSec(s.measuredAt) + '</td>'
        + '<td class="mono" style="color:' + (s.temperatureC >= 70 ? toneColor("bad") : "inherit") + '">'
        + fmtMetric(s.temperatureC, 1) + '</td>'
        + '<td class="mono" style="color:' + (s.vibrationMmS >= 3 ? toneColor("bad") : "inherit") + '">'
        + fmtMetric(s.vibrationMmS, 2) + '</td>'
        + '<td class="mono" style="color:' + (s.currentA >= 15 ? toneColor("bad") : "inherit") + '">'
        + fmtMetric(s.currentA, 1) + '</td>'
        + '<td class="mono">' + fmtNum(s.rotationalSpeedRpm, 0) + '</td>'
        + '<td class="mono mini">' + h(s.sampleId || "—") + '</td></tr>').join("")
    + '</tbody></table></div></div>';
  return html;
}

/* ---------- Tab 3：健康评估历史 ---------- */
function detailHealthHtml(ev){
  const list = state.detailEvaluations || [];
  let html = '<div class="card">' + sect("健康评估历史", "B 服务 " + list.length + " 条")
    + noticeLive("数据来源：B <span class=\"mono\">GET /api/v1/health-evaluations?equipmentId=</span>（本次新增的只读接口）。");
  if (!list.length) {
    html += emptyBox("该设备暂无评估历史", "注入一次数据后 B 会记录评估结果");
  } else {
    const scores = list.map(e => Number(e.healthScore)).filter(Number.isFinite);
    html += '<div class="mini" style="margin-bottom:10px">'
      + '样本次数 <b>' + list.length + '</b> · 最新 <b>' + fmtNum(scores[0], 1) + '</b>'
      + ' · 最低 <b>' + fmtNum(Math.min.apply(null, scores), 1) + '</b>'
      + ' · 平均 <b>' + fmtNum(scores.reduce((a,b)=>a+b,0) / scores.length, 1) + '</b></div>';
    html += '<div class="tbl-wrap"><table><thead><tr><th>时间</th><th>健康分</th><th>等级</th>'
      + '<th>疑似故障</th><th>趋势</th><th>关联预警</th><th>模型</th></tr></thead><tbody>'
      + list.map(e => '<tr>'
          + '<td class="mono mini">' + fmtTimeSec(e.evaluatedAt) + '</td>'
          + '<td class="mono" style="color:' + toneColor(
              Number(e.healthScore) >= 80 ? "ok" : Number(e.healthScore) >= 60 ? "warn" : "bad") + '">'
          + fmtNum(e.healthScore, 1) + '</td>'
          + '<td>' + tag("riskLevel", e.riskLevel) + '</td>'
          + '<td class="mini">' + h(e.suspectedFault || "—") + '</td>'
          + '<td class="mini">' + h(e.trend && e.trend !== "UNKNOWN" ? e.trend : "—") + '</td>'
          + '<td class="mono mini">' + (e.warningId
              ? '<a href="#/warn/' + h(e.warningId) + '">' + h(e.warningId) + '</a>' : "—") + '</td>'
          + '<td class="mono mini">' + h(e.modelVersion || "—") + '</td></tr>').join("")
      + '</tbody></table></div>';
  }
  html += '</div>';
  return html;
}

/* ---------- Tab 4：预警记录 ---------- */
function detailWarnsHtml(eqId){
  const ws = state.detailWarnings || [];
  let html = '<div class="card">' + sect("预警记录", "该设备 " + ws.length + " 条");
  if (state.warnDenied) {
    html += emptyBox("当前角色无预警查看权限（WARNING_READ）",
      "预警列表受权限门禁保护");
  } else if (!ws.length) {
    html += emptyBox("该设备暂无预警记录", "注入异常数据可创建预警");
  } else {
    const active = ws.filter(w => ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER"].includes(w.status));
    html += '<div class="mini" style="margin-bottom:10px">活跃 '
      + '<b style="color:' + toneColor(active.length ? "bad" : "ok") + '">' + active.length + '</b>'
      + ' 条 · 已闭环 <b>' + (ws.length - active.length) + '</b> 条</div>';
    html += '<div class="tbl-wrap"><table><thead><tr><th>预警编号</th><th>等级</th><th>健康分</th>'
      + '<th>疑似故障</th><th>状态</th><th>关联工单</th><th>时间</th></tr></thead><tbody>'
      + ws.map(w => '<tr class="row-link" onclick="navigate(\'warn/' + h(w.warningId) + '\')">'
          + '<td class="mono">' + h(w.warningId) + '</td>'
          + '<td>' + tag("riskLevel", w.riskLevel) + '</td>'
          + '<td class="mono" style="color:' + toneColor(
              Number(w.healthScore) >= 80 ? "ok" : Number(w.healthScore) >= 60 ? "warn" : "bad") + '">'
          + fmtNum(w.healthScore, 1) + '</td>'
          + '<td class="mini">' + h(w.suspectedFault || "—") + '</td>'
          + '<td>' + tag("warningStatus", w.status) + '</td>'
          + '<td class="mono mini">' + (w.linkedOrderId
              ? '<a href="#/order/' + h(w.linkedOrderId) + '">' + h(w.linkedOrderId) + '</a>' : "—") + '</td>'
          + '<td class="mini">' + relTime(w.warningAt) + '</td></tr>').join("")
      + '</tbody></table></div>';
  }
  html += '</div>';
  return html;
}

/* ---------- Tab 5：维修工单 ---------- */
function detailOrdersHtml(eqId){
  const os = state.detailOrders || [];
  let html = '<div class="card">' + sect("维修工单", "该设备 " + os.length + " 张");
  if (!os.length) {
    html += emptyBox("该设备暂无工单", "预警触发后 C 会自动建单，也可手工新建");
  } else {
    html += '<div class="tbl-wrap"><table><thead><tr><th>工单号</th><th>标题</th><th>优先级</th>'
      + '<th>状态</th><th>来源</th><th>负责人</th><th>创建</th></tr></thead><tbody>'
      + os.map(o => '<tr class="row-link" onclick="navigate(\'order/' + h(o.orderId) + '\')">'
          + '<td class="mono">' + h(o.orderId) + '</td>'
          + '<td>' + h(o.title || "—") + '</td>'
          + '<td>' + tag("workOrderPriority", o.priority) + '</td>'
          + '<td>' + tag("workOrderStatus", o.status) + '</td>'
          + '<td>' + tag("workOrderSource", o.sourceType) + '</td>'
          + '<td class="mono mini">' + h(o.assigneeId || "—") + '</td>'
          + '<td class="mini">' + fmtTime(o.createdAt) + '</td></tr>').join("")
      + '</tbody></table></div>';
  }
  html += '</div>';
  return html;
}

/* ---------- Tab 6：设备档案（规划中：需要扩模型） ---------- */
function detailProfileHtml(eq){
  const fields = [
    ["设备编号", eq.equipmentId, "已实现"],
    ["设备名称", eq.name, "已实现"],
    ["设备类型", eq.equipmentType, "已实现"],
    ["所属产线", eq.productionLineId, "已实现"],
    ["安装位置", eq.location, "已实现"],
    ["制造商", eq.manufacturer, "已实现"],
    ["型号", eq.model, "已实现"],
    ["责任部门", eq.responsibleDepartment, "已实现"],
    ["运行状态", enumZh("equipmentStatus", eq.currentStatus), "已实现"],
    ["主数据在册", eq.enabled === false ? "已停用" : "已启用", "已实现"],
    ["版本号", "v" + eq.version, "已实现"],
    ["出厂编号 serialNumber", "—", "待扩模型"],
    ["投运日期 commissionedAt", "—", "待扩模型"],
    ["资产原值 assetValue", "—", "待扩模型"],
    ["保修截止 warrantyUntil", "—", "待扩模型"],
    ["说明书 / 图纸附件", "—", "待扩模型"],
  ];
  let html = '<div class="card">' + sect("设备档案", "运行态字段已实现 · 静态档案字段待扩模型")
    + noticePlan("行进中 · 需扩模型 — 当前 Equipment 模型只有运行态字段（编号 / 名称 / 位置 / 状态 / "
      + "启用 / 版本），<b>没有</b>厂商、型号、出厂编号、投运日期、资产原值等静态档案字段。"
      + "落地需要：① 新增 <span class=\"mono\">equipment_profile</span> 表（1:1 关联）或扩列；"
      + "② 提供 <span class=\"mono\">GET/PUT /api/v1/equipment/{id}/profile</span>；"
      + "③ 演示库走 <span class=\"mono\">scripts/reset_demo.py</span> 重建路径。")
    + '<div class="tbl-wrap"><table><thead><tr><th>字段</th><th>值</th><th style="width:110px">状态</th>'
    + '</tr></thead><tbody>'
    + fields.map(f => '<tr><td>' + h(f[0]) + '</td><td class="mono">' + h(f[1]) + '</td>'
        + '<td>' + (f[2] === "已实现" ? '<span class="pill b-ok">已实现</span>'
            : '<span class="pill b-dim">' + h(f[2]) + '</span>') + '</td></tr>').join("")
    + '</tbody></table></div></div>';
  return html;
}

/* B scoring.py 的权重与阈值（口径参照，非本机实测值） */
const SCORE_METRICS = [
  { zh:"振动速度", unit:"mm·s⁻¹", normal:"3.0", full:"6.0", weight:"40%", fault:"主轴轴承振动异常" },
  { zh:"轴承温度", unit:"℃",       normal:"70",  full:"90",  weight:"25%", fault:"设备温升异常" },
  { zh:"运行电流", unit:"A",       normal:"15",  full:"30",  weight:"20%", fault:"驱动电流异常" },
  { zh:"转速偏离", unit:"%（相对额定）", normal:"5%", full:"15%", weight:"15%", fault:"转速偏差异常" },
];

function row2(k, v){
  return '<tr><td class="mini" style="width:120px">' + k + '</td><td>' + v + '</td></tr>';
}

window.detailTab = function (t) {
  state.detailTab = t;
  route(true);
};

window.recoverFromDetail = async function () {
  if (!state.openEq) return;
  const yes = await confirmBox("恢复正常数据",
    "将向 <b>" + h(state.openEq) + "</b> 注入一组正常遥测（65.2℃ / 3.4 mm·s⁻¹）：<br><br>"
    + "• 设备状态复位为 <b>运行中</b>（即使是维修中或已停止）<br>"
    + "• B 重新评分；若判定为 <b>LOW</b>，活跃预警自动闭环<br>"
    + "• 关联工单若仍在早期三态（待确认/待派单/待接单）会被系统自动结单", { okText: "注入正常数据" });
  if (!yes) return;
  await injectData("normal", state.openEq);
  await loadCore();
  route(true);
};
