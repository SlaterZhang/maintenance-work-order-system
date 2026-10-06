/* 设备详情：详情刷新、预警卡片（P2-9）、遥测图表（P2-10 force 参数生效） */
"use strict";
async function openEquipment(eqId){
  state.openEq = eqId;
  state.chartData = []; state.telemetrySeen = new Set();   // 切换设备：图表重新加载
  showView("equipment");
  await refreshEquipmentDetail();
  await loadTelemetry(true);
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
    // 预警查询受 WARNING_READ 门禁：无权限（403）时回退到最新健康评估数据
    let w = null;
    try {
      const warnPage = await api("b", "/api/v1/warnings?equipmentId=" + state.openEq + "&pageSize=1", {headers: authHeaders()});
      w = (warnPage.items || [])[0];
    } catch (e) { w = null; }
    const fallback = state.healthMap[state.openEq];
    $("eq-health").textContent = w ? (w.healthScore == null ? "--" : w.healthScore) : (fallback ? fallback.score : "--");
    const box = $("judge");
    const statusZh = (st) => WARN_STATUS_ZH[st] || st;
    if (w) {
      box.innerHTML =
        `<div class="row"><span class="k">最近预警</span><span class="v"><span class="risk r-${esc(w.riskLevel)}">${esc(w.riskLevel)}</span> ${esc(w.warningId)} · ${esc(statusZh(w.status))}</span></div>` +
        `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:20px">${esc(w.healthScore)}</span></div>` +
        `<div class="row"><span class="k">系统判断（疑似故障）</span><span class="v">${esc(w.suspectedFault)}</span></div>` +
        `<div class="row"><span class="k">建议措施</span><span class="v">${esc(w.recommendedAction)}</span></div>`;
    } else if (fallback) {
      box.innerHTML =
        `<div class="row"><span class="k">最新评估</span><span class="v"><span class="risk r-${esc(fallback.riskLevel)}">${esc(fallback.riskLevel)}</span>` +
        (state.warnDenied ? ` <span class="mini">（预警明细需 WARNING_READ 权限）</span>` : ``) + `</span></div>` +
        `<div class="row"><span class="k">健康度</span><span class="v health" style="font-size:20px">${esc(fallback.score)}</span></div>` +
        `<div class="row"><span class="k">系统判断（疑似故障）</span><span class="v">${esc(fallback.fault || "指标正常")}</span></div>` +
        `<div class="row"><span class="k">建议措施</span><span class="v">${esc(fallback.action || "--")}</span></div>`;
    } else {
      box.innerHTML = '<div class="empty">暂无预警，设备运行正常</div>';
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

function chartOption(title, unit){
  let ml = [];
  if (title === "温度") {
    ml = [
      {yAxis:80,lineStyle:{color:"red",type:"dashed",width:1},label:{show:true,formatter:"高温{c}"}},
      {yAxis:50,lineStyle:{color:"blue",type:"dashed",width:1},label:{show:true,formatter:"低温{c}"}},
    ];
  } else if (title === "振动") {
    ml = [{yAxis:6,lineStyle:{color:"red",type:"dashed",width:1},label:{show:true,formatter:"阈值{c}"}}];
  } else if (title === "电流") {
    ml = [{yAxis:20,lineStyle:{color:"red",type:"dashed",width:1},label:{show:true,formatter:"阈值{c}"}}];
  }
  return {
    grid:{left:44,right:14,top:26,bottom:26},
    tooltip:{trigger:"axis"},
    xAxis:{type:"category",data:[],axisLabel:{color:"#8ba0c0",fontSize:10,rotate:28}},
    yAxis:{type:"value",name:unit,nameTextStyle:{color:"#8ba0c0"},axisLabel:{color:"#8ba0c0"}},
    series:[{type:"line",data:[],smooth:true,symbol:"none",
      lineStyle:{color:"#39d2ff",width:2},
      areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,
        [{offset:0,color:"rgba(57,210,255,.35)"},{offset:1,color:"rgba(57,210,255,0)"}])},
      markLine:ml.length ? {data:ml} : undefined}],
  };
}

function ensureCharts(){
  if (state.chartOk || typeof echarts === "undefined") return;
  state.chartOk = true;
  const defs = [["chart-temp","温度","℃"],["chart-vib","振动","mm/s"],["chart-curr","电流","A"]];
  for (const [id, name, unit] of defs) {
    state.charts[id] = echarts.init($(id));
    state.charts[id].setOption(chartOption(name, unit));
  }
}

/* P2-10：force=true 时清空增量缓存全量重载（此前参数被忽略） */
async function loadTelemetry(force){
  if (!state.openEq) return;
  ensureCharts();
  if (typeof echarts === "undefined") {
    ["chart-temp","chart-vib","chart-curr"].forEach(id => {
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

function updateCharts(){
  const items = state.chartData;
  const times = items.map(i => (i.measuredAt || "").replace("T"," ").replace("Z","").slice(5,19));
  const series = {
    "chart-temp": items.map(i => i.temperatureC),
    "chart-vib":  items.map(i => i.vibrationMmS),
    "chart-curr": items.map(i => i.currentA),
  };
  for (const id of Object.keys(state.charts)) {
    state.charts[id].setOption({xAxis:{data:times}, series:[{data:series[id]}]});
  }
}
