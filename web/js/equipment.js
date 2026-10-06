/* 设备详情：详情刷新、预警卡片（P2-9）、遥测图表（P2-10）、
   退化趋势外推可视化（阶段3：回归外推虚线 + 满扣阈值线 + B 预测结论） */
"use strict";
/* B 规则引擎阈值口径（与 B 服务 scoring.py 一致）：
   [正常线, 满扣(报警终点)线] —— 图表阈值线与趋势外推共用 */
const METRIC_LIMITS = {
  "chart-temp": {normal: 70, full: 90, label: "温度"},
  "chart-vib":  {normal: 3.0, full: 6.0, label: "振动"},
  "chart-curr": {normal: 15, full: 30, label: "电流"},
};
/* 图表外推时长（小时）：虚线延伸 12 小时，与满扣阈值线的交点即"预计触阈值" */
const PROJECTION_HOURS = 12;

async function openEquipment(eqId){
  state.openEq = eqId;
  state.chartData = []; state.telemetrySeen = new Set();   // 切换设备：图表重新加载
  showView("equipment");
  await refreshEquipmentDetail();
  await loadTelemetry(true);
}

/* B 趋势字段的中文结论（与 B 服务 trend_conclusion_zh 同口径，前端仅展示） */
function trendConclusionZh(ev){
  if (!ev || !ev.trend || ev.trend === "UNKNOWN") return "";
  if (ev.trend === "IMPROVING") return "趋势预测：各项指标整体好转（IMPROVING）";
  if (ev.trend === "STABLE") return "趋势预测：各项指标平稳（STABLE）";
  // DEGRADING
  const metricZh = {temperature: "温度", vibration: "振动", current: "电流"}[ev.trendMetric];
  const unit = {temperature: "℃/天", vibration: "mm·s⁻¹/天", current: "A/天"}[ev.trendMetric];
  if (ev.trendMetric && ev.predictedDaysToThreshold != null) {
    return `趋势预测：${metricZh}以约 ${ev.trendRatePerDay}${unit} 的速率上行，` +
      `预计 ${ev.predictedDaysToThreshold} 天后达到 ${ev.trendThreshold} 满扣阈值，建议提前安排检修`;
  }
  return "趋势预测：关键指标持续上行，已越过满扣阈值，建议立即处置";
}

async function refreshEquipmentDetail(){
  if (!state.openEq) return;
  try {
    const eq = await api("a", "/api/v1/equipment/" + state.openEq, {headers: authHeaders()});
    $("eq-title").textContent = eq.equipmentId + " " + (eq.name || "");
    $("eq-sub").textContent = `${eq.productionLineId || ""} · ${eq.location || ""}`;
    const statusEl = $("eq-status");
    statusEl.textContent = EQ_STATUS_ZH[eq.currentStatus] || eq.currentStatus;
    statusEl.style.color = EQ_STATUS_COLOR[eq.currentStatus] || "var(--dim)";
    // B 最新健康评估（阶段3：携带退化趋势外推结论），优先于预警快照展示
    let latestEval = null;
    try {
      latestEval = await api("b", "/api/v1/health-evaluations/latest?equipmentId=" + state.openEq,
          {headers: authHeaders()});
    } catch (e) { latestEval = null; }
    // 预警查询受 WARNING_READ 门禁：无权限（403）时回退到最新评估数据
    let w = null;
    try {
      const warnPage = await api("b", "/api/v1/warnings?equipmentId=" + state.openEq + "&pageSize=1", {headers: authHeaders()});
      w = (warnPage.items || [])[0];
    } catch (e) { w = null; }
    const hasEval = latestEval && latestEval.hasEvaluation;
    $("eq-health").textContent = hasEval ? latestEval.healthScore :
        (w ? (w.healthScore == null ? "--" : w.healthScore) : "--");
    const box = $("judge");
    const statusZh = (st) => WARN_STATUS_ZH[st] || st;
    const trendRow = hasEval ? trendConclusionZh(latestEval) : "";
    const trendBadge = hasEval && latestEval.trend && latestEval.trend !== "UNKNOWN"
        ? `<span class="risk r-${latestEval.trend === "DEGRADING" ? "CRITICAL" : latestEval.trend === "STABLE" ? "MEDIUM" : "LOW"}">${esc(latestEval.trend)}</span>` : "";
    if (w) {
      box.innerHTML =
        `<div class="row"><span class="k">最近预警</span><span class="v"><span class="risk r-${esc(w.riskLevel)}">${esc(w.riskLevel)}</span> ${esc(w.warningId)} · ${esc(statusZh(w.status))}</span></div>` +
        `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:20px">${esc(w.healthScore)}</span></div>` +
        `<div class="row"><span class="k">系统判断（疑似故障）</span><span class="v">${esc(w.suspectedFault)}</span></div>` +
        `<div class="row"><span class="k">建议措施</span><span class="v">${esc(w.recommendedAction)}</span></div>` +
        (trendRow ? `<div class="row"><span class="k">退化趋势</span><span class="v">${trendBadge} <span class="mini">${esc(trendRow)}</span></span></div>` : "");
    } else if (hasEval) {
      box.innerHTML =
        `<div class="row"><span class="k">最新评估</span><span class="v"><span class="risk r-${esc(latestEval.riskLevel)}">${esc(latestEval.riskLevel)}</span>` +
        (latestEval.warningId ? ` · 关联预警 ${esc(latestEval.warningId)}` : ` <span class="mini">（无活跃预警）</span>`) + `</span></div>` +
        `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:20px">${esc(latestEval.healthScore)}</span></div>` +
        `<div class="row"><span class="k">系统判断（疑似故障）</span><span class="v">${esc(latestEval.suspectedFault || "指标正常")}</span></div>` +
        `<div class="row"><span class="k">建议措施</span><span class="v">${esc(latestEval.recommendedAction || "--")}</span></div>` +
        (trendRow ? `<div class="row"><span class="k">退化趋势</span><span class="v">${trendBadge} <span class="mini">${esc(trendRow)}</span></span></div>` : "");
    } else {
      const fallback = state.healthMap[state.openEq];
      if (fallback) {
        box.innerHTML =
          `<div class="row"><span class="k">最新评估</span><span class="v"><span class="risk r-${esc(fallback.riskLevel)}">${esc(fallback.riskLevel)}</span></span></div>` +
          `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:20px">${esc(fallback.score)}</span></div>` +
          `<div class="row"><span class="k">系统判断（疑似故障）</span><span class="v">${esc(fallback.fault || "指标正常")}</span></div>` +
          `<div class="row"><span class="k">建议措施</span><span class="v">${esc(fallback.action || "--")}</span></div>`;
      } else {
        box.innerHTML = '<div class="empty">暂无评估，设备运行正常（注入数据可触发评估）</div>';
      }
    }
    renderEqWarnCard(w);
  } catch (e) {
    toast("设备详情加载失败：" + e.message, "err");
  }
}

function renderEqWarnCard(w){
  const card = $("eq-warn-card");
  if (!card) return;
  if (!w) { card.style.display = "none"; return; }
  card.style.display = "block";
  const riskColor = {CRITICAL:"#ff5050", HIGH:"#ffa500", MEDIUM:"#ffc800", LOW:"#50c878"}[w.riskLevel] || "";
  card.style.borderLeft = riskColor ? `4px solid ${riskColor}` : "";
  const statusZh = WARN_STATUS_ZH[w.status] || w.status;
  card.innerHTML =
    `<h2 class="sec">当前预警详情 <span class="mini">（B 故障预警服务）</span></h2>` +
    `<div class="judge">` +
      `<div class="row"><span class="k">预警编号</span><span class="v"><b>${esc(w.warningId)}</b></span></div>` +
      `<div class="row"><span class="k">风险等级</span><span class="v"><span class="risk r-${esc(w.riskLevel)}">${esc(w.riskLevel)}</span></span></div>` +
      `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:18px">${esc(w.healthScore)}</span></div>` +
      `<div class="row"><span class="k">疑似故障</span><span class="v">${esc(w.suspectedFault)}</span></div>` +
      `<div class="row"><span class="k">建议措施</span><span class="v">${esc(w.recommendedAction)}</span></div>` +
      `<div class="row"><span class="k">预警时间</span><span class="v">${esc((w.warningAt || "").replace("T", " ").replace("Z", ""))}</span></div>` +
      `<div class="row"><span class="k">状态</span><span class="v">${esc(statusZh)}</span></div>` +
    `</div>`;
}

function chartOption(id){
  const lim = METRIC_LIMITS[id] || {normal: null, full: null};
  const markData = [];
  if (lim.normal != null) markData.push({
    yAxis: lim.normal, lineStyle: {color: "#39d2ff", type: "dashed", width: 1},
    label: {show: true, formatter: `正常 ${lim.normal}`, color: "#8ba0c0", fontSize: 10},
  });
  if (lim.full != null) markData.push({
    yAxis: lim.full, lineStyle: {color: "red", type: "dashed", width: 1.2},
    label: {show: true, formatter: `满扣 ${lim.full}`, color: "#ff5c5c", fontSize: 10},
  });
  return {
    grid: {left: 44, right: 14, top: 26, bottom: 26},
    tooltip: {trigger: "axis"},
    xAxis: {type: "category", data: [], axisLabel: {color: "#8ba0c0", fontSize: 10, rotate: 28}},
    yAxis: {type: "value", name: "", nameTextStyle: {color: "#8ba0c0"}, axisLabel: {color: "#8ba0c0"}},
    series: [
      {   // 实测序列
        name: "实测", type: "line", data: [], smooth: true, symbol: "none",
        lineStyle: {color: "#39d2ff", width: 2},
        areaStyle: {color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{offset: 0, color: "rgba(57,210,255,.35)"}, {offset: 1, color: "rgba(57,210,255,0)"}])},
        markLine: markData.length ? {data: markData, symbol: "none"} : undefined,
      },
      {   // 阶段3：线性回归外推（虚线）——与满扣阈值线的交点即预计触阈值
        name: "趋势外推", type: "line", data: [], smooth: false, symbol: "none",
        lineStyle: {color: "#ffc53d", type: "dashed", width: 1.6},
        itemStyle: {color: "#ffc53d"},
      },
    ],
  };
}

function ensureCharts(){
  if (state.chartOk || typeof echarts === "undefined") return;
  state.chartOk = true;
  for (const id of Object.keys(METRIC_LIMITS)) {
    state.charts[id] = echarts.init($(id));
    state.charts[id].setOption(chartOption(id));
  }
}

/* P2-10：force=true 时清空增量缓存全量重载（此前参数被忽略） */
async function loadTelemetry(force){
  if (!state.openEq) return;
  ensureCharts();
  if (typeof echarts === "undefined") {
    Object.keys(METRIC_LIMITS).forEach(id => {
      $(id).innerHTML = '<div class="empty">ECharts 本地文件（web/echarts.min.js）加载失败，图表不可用（页面其余功能正常）</div>';
    });
    return;
  }
  if (force) {
    state.chartData = [];
    state.telemetrySeen = new Set();
  }
  try {
    const data = await api("a", "/api/v1/equipment/" + state.openEq + "/telemetry?pageSize=30",
        {headers: authHeaders()});
    const items = (data.items || []).slice().reverse();   // 升序展示
    for (const it of items) {                              // 增量追加未见过的样本
      if (!state.telemetrySeen.has(it.sampleId)) {
        state.telemetrySeen.add(it.sampleId);
        state.chartData.push(it);
      }
    }
    while (state.chartData.length > 30) {                  // 滚动窗口保留最近 30 点
      state.telemetrySeen.delete(state.chartData[0].sampleId);
      state.chartData.shift();
    }
    updateCharts();
  } catch (e) {
    toast("遥测数据加载失败：" + e.message, "err");
  }
}

/* 最小二乘线性拟合（x=毫秒，y=指标值）；返回 {k 斜率/小时, at(h) 预测函数} */
function fitSlope(points){
  const n = points.length;
  if (n < 2) return null;
  const t0 = points[0][0];
  const xs = points.map(p => (p[0] - t0) / 3600000);
  const ys = points.map(p => p[1]);
  const mx = xs.reduce((s, x) => s + x, 0) / n;
  const my = ys.reduce((s, y) => s + y, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (ys[i] - my); den += (xs[i] - mx) ** 2; }
  if (den <= 0) return null;
  const k = num / den;
  return {k, at: h => my + k * (h - mx)};
}

function updateCharts(){
  const items = state.chartData;
  if (!items.length) return;
  const times = items.map(i => (i.measuredAt || "").replace("T", " ").replace("Z", "").slice(5, 19));
  const lastTime = new Date(items[items.length - 1].measuredAt.replace("Z", ""));
  // 外推时段的时间标签（每小时一格，与实测序列同轴）
  const projLabels = [];
  for (let h = 1; h <= PROJECTION_HOURS; h++) {
    const t = new Date(lastTime.getTime() + h * 3600000);
    projLabels.push(
      `${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")} ` +
      `${String(t.getHours()).padStart(2, "0")}:00:00`);
  }
  const allTimes = times.concat(projLabels);
  const pickers = {
    "chart-temp": it => it.temperatureC,
    "chart-vib":  it => it.vibrationMmS,
    "chart-curr": it => it.currentA,
  };
  for (const id of Object.keys(state.charts)) {
    const values = items.map(pickers[id]);
    const points = items
        .map(it => [new Date(String(it.measuredAt || "").replace("Z", "")).getTime(),
                    pickers[id](it)])
        .filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));
    const fit = fitSlope(points);
    let proj;
    if (fit && fit.k > 0) {   // 仅上行做外推（下行/平稳不画预测线）
      const lastVal = values[values.length - 1];
      const totalHours = points[points.length - 1][0] - points[0][0];
      proj = Array(times.length - 1).fill(null).concat([lastVal]);
      for (let h = 1; h <= PROJECTION_HOURS; h++) {
        proj.push(Math.max(0, fit.at(totalHours + h)));
      }
    } else {
      proj = Array(allTimes.length).fill(null);
    }
    state.charts[id].setOption({
      xAxis: {data: allTimes},
      series: [{data: values}, {data: proj}],
    });
  }
}
