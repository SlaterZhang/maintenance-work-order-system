/* ============================================================================
 * 演进页共享工具（智能分析 4 页 + 模型与数据 3 页）
 *
 * ★ 写作纪律（比代码本身更重要）：
 *   这 7 页在原型里是"设计稿"，画了很多曲线与指标数字，而那些数字全是编的。
 *   原样搬进真实前端等于给用户看假仪表盘，比不画更糟（工程上会据此决策）。
 *   所以本文件的每一页都遵守同一条规则：
 *     · 能用真实数据算出来的，**当场算**；
 *     · 算不出来但能说清"为什么算不出来"的，如实说明 + 给落地路径；
 *     · 绝不编造读数、绝不画一个假装有数据的图。
 *
 *   真实可算的部分（已用同一算法在后端实测验证）：
 *     · 遥测质量：缺失率 / 越物理范围 / 重复 / 采样间隔稳定性 ← 596 条真实样本
 *     · 异常点：3σ 与 z-norm 滑动窗口 Matrix Profile discord ← 真算
 *     · 归因分解：scoring.py 的 ratios/penalties 权重公式 ← 与 B 一致
 *     · RUL 趋势：trend.py 的 trendRatePerDay / predictedDaysToThreshold ← 真字段
 *     · 对账：B health_evaluation/warning 与 C work_order 三方交叉 ← 真表
 * ==========================================================================*/

// ── 数据装载 ───────────────────────────────────────────────────────────
/** 拉单台设备全部样本（A 支持 pageSize=100，实测 81 条一次取回） */
async function loadTelemetryWindow(eqId, pageSize){
  const d = await api("a", "/api/v1/equipment/" + encodeURIComponent(eqId)
    + "/telemetry?pageSize=" + (pageSize || 100), { headers: authHeaders() });
  // ⚠ 接口把 equipmentId 放在**响应顶层**，items 每一条都没有该字段 ——
  // 必须在此补写，否则按 equipmentId 分组会把 8 台设备全归进 undefined 一桶。
  return (d.items || []).map(it => Object.assign({ equipmentId: eqId }, it))
    .reverse();   // 按时间升序
}

/** 每台设备的完整遥测窗口 → state.telemetryWindowMap（8 台并发可行） */
async function loadAllTelemetryWindows(){
  const eqs = state.equipment || [];
  state.telemetryWindowMap = state.telemetryWindowMap || {};
  await Promise.all(eqs.map(async eq => {
    try {
      state.telemetryWindowMap[eq.equipmentId] = await loadTelemetryWindow(eq.equipmentId, 100);
    } catch (e) { state.telemetryWindowMap[eq.equipmentId] = []; }
  }));
}

/** 全厂评估历史（loadEvaluations 只返回、不写 state，故此处自行落库） */
async function ensureEvalHistory(){
  if ((state.evaluations || []).length) return state.evaluations;
  try { state.evaluations = await loadEvaluations(""); }
  catch (e) { state.evaluations = state.evaluations || []; }
  return state.evaluations;
}

/** 全部真实样本的扁平数组 */
function allSamples(){
  const m = state.telemetryWindowMap || {};
  let out = [];
  Object.keys(m).forEach(id => { out = out.concat(m[id] || []); });
  return out;
}

/** 样本最多的一台设备（让统计有足够数据可算） */
function richestEq(){
  const m = state.telemetryWindowMap || {};
  let best = null, bestN = -1;
  Object.keys(m).forEach(id => {
    const n = (m[id] || []).length;
    if (n > bestN) { bestN = n; best = id; }
  });
  return best;
}

// ── 真实统计（阈值口径与 scoring.py 一致）──────────────────────────────
// ak = 归因分解用的键名（scoring.py 的 ratios/penalties 用 vibration/temperature/
// current/speed，与遥测字段名不同 —— 必须显式映射，否则整行会静默消失）。
const PLAN_METRICS = [
  { key:"temperatureC",       ak:"temperature", zh:"温度", unit:"℃",      normal:70,   full:90,   min:-20, max:400 },
  { key:"vibrationMmS",       ak:"vibration",   zh:"振动", unit:"mm·s⁻¹", normal:3.0,  full:6.0,  min:0,   max:200 },
  { key:"currentA",           ak:"current",     zh:"电流", unit:"A",       normal:15,   full:30,   min:0,   max:500 },
  { key:"rotationalSpeedRpm", ak:"speed",       zh:"转速", unit:"rpm",     normal:null, full:null, min:0,   max:50000 },
];

function pMean(a){ return a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0; }
function pSd(a){
  if (a.length < 2) return 0;
  const m = pMean(a);
  return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / a.length);
}

/** 真实数据质量指标（全部当场算） */
function realDataQuality(){
  const samples = allSamples();
  const n = samples.length;
  if (!n) return null;
  let missing = 0, outOfRange = 0, dupIds = 0;
  const seen = new Set();
  samples.forEach(s => {
    PLAN_METRICS.forEach(m => {
      const v = s[m.key];
      if (v === null || v === undefined) { missing++; return; }
      if (v < m.min || v > m.max) outOfRange++;
    });
    if (s.sampleId) { if (seen.has(s.sampleId)) dupIds++; else seen.add(s.sampleId); }
  });

  const byEq = {};
  samples.forEach(s => { (byEq[s.equipmentId] = byEq[s.equipmentId] || []).push(s); });
  const intervalStats = Object.keys(byEq).map(eq => {
    const ts = byEq[eq].map(s => Date.parse(s.measuredAt))
      .filter(x => !isNaN(x)).sort((a, b) => a - b);
    const gaps = [];
    for (let i = 1; i < ts.length; i++) gaps.push((ts[i] - ts[i-1]) / 1000);
    const sorted = gaps.slice().sort((a, b) => a - b);
    const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    return {
      eq: eq, samples: byEq[eq].length, gaps: gaps.length, medianSec: med,
      irregular: gaps.filter(g => med > 0 && Math.abs(g - med) / med > 0.10).length,
      minSec: gaps.length ? Math.min.apply(null, gaps) : 0,
      maxSec: gaps.length ? Math.max.apply(null, gaps) : 0,
    };
  });

  const cells = n * PLAN_METRICS.length;
  return {
    samples: n, cells: cells, missing: missing, outOfRange: outOfRange, dupIds: dupIds,
    equipments: Object.keys(byEq).length,
    missingRate: missing / cells * 100,
    // 转速恒定、方差为 0，3σ 判定天然不参与，故分母要把它剔掉
    scoredCells: n * (PLAN_METRICS.length - 1),
    intervalStats: intervalStats,
  };
}

/** 真实 3σ 越限点（转速恒定、方差为 0，不参与） */
function realOutliers(){
  const byEq = {};
  allSamples().forEach(s => { (byEq[s.equipmentId] = byEq[s.equipmentId] || []).push(s); });
  const out = [];
  Object.keys(byEq).forEach(eq => {
    PLAN_METRICS.forEach(m => {
      if (m.key === "rotationalSpeedRpm") return;
      const vals = byEq[eq].map(s => s[m.key]).filter(v => v !== null && v !== undefined);
      if (vals.length < 10) return;
      const mu = pMean(vals), sig = pSd(vals);
      if (sig <= 0) return;
      byEq[eq].forEach(s => {
        const v = s[m.key];
        if (v === null || v === undefined) return;
        if (Math.abs(v - mu) > 3 * sig) {
          out.push({ equipmentId: eq, metric: m, value: v, measuredAt: s.measuredAt,
                     mu: mu, sd: sig, sigma: Math.abs(v - mu) / sig });
        }
      });
    });
  });
  return out.sort((a, b) => b.sigma - a.sigma);
}

/** 真实 Matrix Profile discord（z-norm 滑动窗口）。
 *  零训练基线的核心算法——本页真的在浏览器里算，不是示意曲线。 */
function anomalyDiscords(eqId, win){
  const rows = (state.telemetryWindowMap || {})[eqId] || [];
  const m = win || 6;
  const series = rows.map(r => r.temperatureC).filter(v => v !== null && v !== undefined);
  if (series.length < m + 4) return null;
  const znorm = w => {
    const mu = pMean(w), s = pSd(w);
    return s > 1e-9 ? w.map(x => (x - mu) / s) : w.map(() => 0);
  };
  const W = [];
  for (let i = 0; i + m <= series.length; i++) W.push(znorm(series.slice(i, i + m)));
  const P = [];
  for (let i = 0; i < W.length; i++) {
    let best = Infinity;
    for (let j = 0; j < W.length; j++) {
      if (Math.abs(i - j) < Math.floor(m / 2)) continue;
      let d = 0;
      for (let k = 0; k < m; k++) d += (W[i][k] - W[j][k]) * (W[i][k] - W[j][k]);
      d = Math.sqrt(d);
      if (d < best) best = d;
    }
    P.push(best === Infinity ? 0 : best);
  }
  const idx = P.map((v, i) => i).sort((a, b) => P[b] - P[a]);
  const mu = pMean(series), sig = pSd(series);
  const s3 = [];
  if (sig > 0) {
    series.forEach((v, i) => {
      if (Math.abs(v - mu) > 3 * sig) s3.push({ measuredAt: rows[i].measuredAt, value: v });
    });
  }
  return {
    windows: W.length, win: m, n: series.length,
    profileMin: Math.min.apply(null, P), profileMax: Math.max.apply(null, P),
    profileMean: pMean(P),
    discords: idx.slice(0, 3).map(i => ({
      index: i, measuredAt: rows[i] ? rows[i].measuredAt : null, profile: P[i],
      segment: series.slice(i, i + m).map(v => Math.round(v * 10) / 10),
    })),
    sigma3: s3, series: series, times: rows.map(r => r.measuredAt),
  };
}

// ── 真实归因分解（照 scoring.py 的权重与比值公式）─────────────────────
const PLAN_WEIGHTS = { vibration:40, temperature:25, current:20, speed:15 };
const PLAN_ALARM_RATIO = 1.0, PLAN_TRIP_RATIO = 1.5;
const PLAN_CAP_ALARM = 59.9, PLAN_CAP_TRIP = 39.9;
const PLAN_FAULT_ZH = {
  vibration:"主轴轴承振动异常", temperature:"设备温升异常",
  current:"驱动电流异常", speed:"转速偏差异常",
};
const PLAN_METRIC_ZH = { vibration:"振动", temperature:"温度", current:"电流", speed:"转速" };

function rawRatio(value, normal, full){ return (value - normal) / (full - normal); }

/** 对一条真实样点做四指标分解 */
function attributeSample(s){
  const ratios = {
    vibration:   rawRatio(s.vibrationMmS, 3.0, 6.0),
    temperature: rawRatio(s.temperatureC, 70, 90),
    current:     rawRatio(s.currentA, 15, 30),
  };
  if (s.rotationalSpeedRpm !== null && s.rotationalSpeedRpm !== undefined) {
    ratios.speed = Math.abs(s.rotationalSpeedRpm - 1500) / 1500;
  }
  const pen = {};
  Object.keys(PLAN_WEIGHTS).forEach(k => {
    const r = ratios[k];
    pen[k] = r === undefined ? 0 : PLAN_WEIGHTS[k] * Math.max(0, Math.min(1, r));
  });
  const sum = Object.keys(pen).reduce((x, k) => x + pen[k], 0);
  const rawScore = Math.max(0, Math.min(100, 100 - sum));
  const rs = Object.keys(ratios).map(k => ratios[k]).filter(r => r !== undefined);
  const anyTrip = rs.some(r => r >= PLAN_TRIP_RATIO);
  const anyAlarm = rs.some(r => r >= PLAN_ALARM_RATIO);
  const cap = anyTrip ? PLAN_CAP_TRIP : (anyAlarm ? PLAN_CAP_ALARM : null);
  const score = cap !== null ? Math.min(rawScore, cap) : rawScore;
  let worst = null, wv = 0;
  Object.keys(pen).forEach(k => { if (pen[k] > wv) { wv = pen[k]; worst = k; } });
  return {
    ratios: ratios, penalties: pen, penaltySum: sum,
    rawScore: Math.round(rawScore * 10) / 10,
    cap: cap, anyTrip: anyTrip, anyAlarm: anyAlarm,
    score: Math.round(score * 10) / 10,
    fault: wv <= 0 ? "未见明显异常特征" : PLAN_FAULT_ZH[worst],
  };
}

/** 温度热力条（真实样点着色；归一区间仅用于视觉分档） */
function planHeatHtml(series, times, lo, hi){
  if (!series || series.length < 4) return emptyBox("样本不足");
  const n = Math.min(series.length, 48);
  const start = series.length - n;
  const cells = [];
  for (let i = start; i < series.length; i++) {
    const v = series[i];
    const r = (v - lo) / ((hi - lo) || 1);
    const col = r >= 1 ? "var(--red)" : r >= 0.55 ? "var(--yellow)"
      : r >= 0.2 ? "var(--cyan)" : "rgba(57,210,255,.28)";
    const t = times && times[i] ? fmtTimeSec(times[i]) : "";
    cells.push('<i title="' + h(t + "  " + fmtNum(v, 1) + "℃") + '" style="background:' + col + '"></i>');
  }
  const first = times && times[start] ? fmtTimeSec(times[start]) : "";
  const last = times && times[times.length-1] ? fmtTimeSec(times[times.length-1]) : "";
  return '<div class="heat-row"><span class="hl">温度 ℃</span>'
    + '<span class="hc">' + cells.join("") + '</span></div>'
    + '<div class="heat-x"><span class="hl"></span>'
    + '<span class="hc"><span>' + h(first) + '</span><span>' + h(last) + '</span></span></div>';
}
