/* ==========================================================================
   charts.js —— 遥测趋势图与外推（设备详情「遥测趋势」Tab 专用）
   --------------------------------------------------------------------------
   从原 equipment.js 抽出：这部分是纯图表逻辑（阈值线 / 线性回归外推 /
   显著性门槛），与页面外壳无关，因此独立成一个模块，详情页直接复用。

   关键修复（2026-10-07，勿回退）：
     1. 外推的单位是**小时**：`totalHours` 用毫秒差除以 3600000。
        早期版本忘了除，12 小时外推被当成 12 毫秒后的值代入，
        算出 5770 万 ℃，Y 轴被撑爆、刻度被裁成 "00,000"、实测曲线压成一条线。
     2. 外推锚定**最后一点**（`lastVal + k*h`）而不是回归线在 x=0 的截距，
        否则接点处会出现跳变。
     3. 上行量不足满扣阈值的 3% 时**不画**外推线，标注"趋势平稳"——
        噪声斜率画出的预测线会误导检修决策。
     4. `grid.containLabel = true` 取代固定 left:44，大数值刻度不再被裁。
     5. `values` 与全局 `times` 等长（缺失留 null），避免某指标缺值时曲线错位。
   ========================================================================== */
"use strict";

/* B 规则引擎阈值口径（与 B 服务 scoring.py 一致）：
   [正常线, 满扣(报警终点)线] —— 图表阈值线与趋势外推共用 */
const METRIC_LIMITS = {
  "chart-temp": {normal: 70, full: 90, label: "温度", unit: "℃", decimals: 1,
                 pick: it => it.temperatureC},
  "chart-vib":  {normal: 3.0, full: 6.0, label: "振动", unit: "mm·s⁻¹", decimals: 2,
                 pick: it => it.vibrationMmS},
  "chart-curr": {normal: 15, full: 30, label: "电流", unit: "A", decimals: 1,
                 pick: it => it.currentA},
};
/* 图表外推时长（小时）：虚线延伸 12 小时，与满扣阈值线的交点即"预计触阈值" */
const PROJECTION_HOURS = 12;
/* 外推显著性门槛：12 小时预计上行量不足"满扣阈值 × 该比例"视为趋势平稳，不画虚线，
   避免用噪声斜率画出误导性的预测线（2026-10-07 图表可读性修复） */
const PROJ_MIN_RISE_RATIO = 0.03;
/* 外推段 X 轴标签间隔（小时）：12 小时只标 4 格，防止刻度挤成一团 */
const PROJ_LABEL_STEP = 3;

/* 数值格式化：按指标小数位渲染，再去掉多余尾零（65.2→"65.2"、60.0→"60"） */
function fmtMetric(v, decimals){
  if (v == null || !Number.isFinite(Number(v))) return "--";
  return String(Number(Number(v).toFixed(decimals)));
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



function chartOption(id){
  const lim = METRIC_LIMITS[id] || {normal: null, full: null, decimals: 1, unit: ""};
  const markData = [];
  if (lim.normal != null) markData.push({
    yAxis: lim.normal, lineStyle: {color: "#39d2ff", type: "dashed", width: 1},
    // 标签贴在线右端内侧，避免被网格右边界裁切（原 end 定位在窄卡片里会出界）
    label: {show: true, position: "insideEndTop", formatter: `正常 ${lim.normal}`, color: "#39d2ff", fontSize: 10},
  });
  if (lim.full != null) markData.push({
    yAxis: lim.full, lineStyle: {color: "red", type: "dashed", width: 1.2},
    label: {show: true, position: "insideEndTop", formatter: `满扣 ${lim.full}`, color: "#ff5c5c", fontSize: 10},
  });
  return {
    // containLabel:true 让 ECharts 按实际刻度文字宽度自适应左边距，
    // 取代原先固定 left:44 —— 修复大数值刻度（100,000）被裁成 "00,000"
    grid: {left: 6, right: 14, top: 34, bottom: 22, containLabel: true},
    legend: {show: true, top: 0, right: 4, itemWidth: 14, itemHeight: 8,
             textStyle: {color: "#8ba0c0", fontSize: 10}},
    tooltip: {trigger: "axis",
              valueFormatter: v => fmtMetric(v, lim.decimals) + (v == null ? "" : " " + lim.unit)},
    xAxis: {type: "category", data: [],
            axisLabel: {color: "#8ba0c0", fontSize: 10, rotate: 0, hideOverlap: true}},
    // scale:true 让 Y 轴按数据范围自适应（而非从 0 起），复现设备正常值时曲线不再压成一条直线
    yAxis: {type: "value", scale: true, splitNumber: 5, name: "", nameTextStyle: {color: "#8ba0c0"},
            axisLabel: {color: "#8ba0c0", fontSize: 10, formatter: v => fmtMetric(v, lim.decimals)}},
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

/* 最小二乘线性拟合（x=毫秒，y=指标值）；返回斜率 k（指标值/小时） */
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
  return {k: num / den};
}

function updateCharts(){
  const items = state.chartData;
  if (!items.length) return;
  // X 轴标签缩短为 "MM-DD HH:MM"，配合 hideOverlap 自动抽稀，避免 30+ 标签互相重叠
  const times = items.map(i => (i.measuredAt || "").replace("T", " ").replace("Z", "").slice(5, 16));
  const lastTime = new Date(items[items.length - 1].measuredAt.replace("Z", ""));
  // 外推时段的时间标签：每 PROJ_LABEL_STEP 小时一格（避免 12 个刻度挤在一起）
  const projLabels = [];
  const projHours = [];
  for (let h = PROJ_LABEL_STEP; h <= PROJECTION_HOURS; h += PROJ_LABEL_STEP) projHours.push(h);
  for (const h of projHours) {
    const t = new Date(lastTime.getTime() + h * 3600000);
    projLabels.push(
      `${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")} ` +
      `${String(t.getHours()).padStart(2, "0")}:00`);
  }
  const allTimes = times.concat(projLabels);
  for (const id of Object.keys(state.charts)) {
    const lim = METRIC_LIMITS[id];
    // values 与全局 times 等长（空值保留 null，ECharts 断线），避免某指标缺值时曲线错位
    const values = items.map(it => {
      const v = lim.pick(it);
      return Number.isFinite(v) ? v : null;
    });
    // 拟合只用有效点（x=毫秒时间戳，y=指标值）
    const points = items
        .map((it, i) => [new Date(String(it.measuredAt || "").replace("Z", "")).getTime(), values[i]])
        .filter(p => Number.isFinite(p[0]) && Number.isFinite(p[1]));
    if (!points.length) continue;
    const lastVal = points[points.length - 1][1];
    const fit = fitSlope(points);
    // 趋势显著性：12 小时预计上行量须达到满扣阈值的 PROJ_MIN_RISE_RATIO 才画外推线，
    // 否则视为平稳（噪声斜率画出的预测线会误导判断）
    const rise12 = fit && fit.k > 0 ? fit.k * PROJECTION_HOURS : 0;
    const minRise = lim.full != null ? lim.full * PROJ_MIN_RISE_RATIO : 0;
    const significant = fit && fit.k > 0 && rise12 >= minRise;
    let proj = Array(allTimes.length).fill(null);
    let note;
    if (significant) {
      const ceil = (lim.full != null ? lim.full : lastVal * 2) * 3;   // 夹限：杜绝离群斜率再次撑爆坐标轴
      proj = Array(times.length - 1).fill(null).concat([lastVal]);
      // 以"当前值 + 拟合斜率×小时"外推，保证预测线从最后一个实测点平滑接出
      for (const h of projHours) proj.push(Math.min(ceil, Math.max(0, lastVal + fit.k * h)));
      note = `12h 预计 ${fmtMetric(lastVal + rise12, lim.decimals)}${lim.unit}`;
    } else {
      note = "趋势平稳，暂不外推";
    }
    state.charts[id].setOption({
      title: {text: note, left: 0, top: 0,
              textStyle: {color: "#8ba0c0", fontSize: 10, fontWeight: "normal"}},
      xAxis: {data: allTimes},
      series: [{data: values}, {data: proj}],
    });
  }
}
