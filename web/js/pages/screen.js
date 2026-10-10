/* ============================================================================
 * 页面：实时监控大屏（#/screen）
 *
 * 数据来源（真实接口，无虚构）：
 *   A GET /api/v1/equipment                     设备清单与运行状态
 *   A GET /api/v1/equipment/{id}/telemetry      每台最新遥测（逐台 pageSize=1）
 *   B GET /api/v1/health-evaluations/latest     最新健康评估
 *   B GET /api/v1/warnings                      活跃预警
 *
 * 说明：A 服务没有"批量取全部设备最新遥测"的接口（契约里只有按设备分页查询），
 * 所以这里沿用 data.js 的 loadLatestTelemetry()：逐台并发取最新样点。8 台设备
 * 完全可行；设备上千台时这里会是瓶颈——那时应新增一个聚合接口，而不是在前端
 * 循环几千次请求（这是本页刻意写明的扩展点）。
 * ==========================================================================*/

// 指标阈值口径与 B 的 scoring.py 一致（振动 3.0/6.0、温度 70/90、电流 15/30）
// 转速不在此列：它是"相对额定转速的偏离比例"，而额定转速是设备属性。
// A 服务的 Equipment 模型没有 ratedSpeed 字段（见 apps/equipment-monitoring/
// src/domain/models.py），B 的 scoring.py:71 把 NOMINAL_SPEED_RPM=1500 全局硬编码。
// 于是给转速按 1500 取色必然是错的：五号离心泵 2900 rpm、七号传送带 420 rpm
// 在各自设备上都是正常工况，却会被判成满扣红线。本页因此只中性展示转速读数，
// 不参与取色与 KPI 判定——宁可不判，也不给假警报。
const SCREEN_METRICS = [
  { key:"vibrationMmS",       zh:"振动", unit:"mm·s⁻¹", normal:3.0,  full:6.0,  dec:1 },
  { key:"temperatureC",       zh:"温度", unit:"℃",      normal:70,   full:90,   dec:1 },
  { key:"currentA",           zh:"电流", unit:"A",       normal:15,   full:30,   dec:1 },
  { key:"rotationalSpeedRpm", zh:"转速", unit:"rpm",     normal:null, full:null, dec:0 },
];

/** 单指标按阈值取色：正常绿 / 越正常线黄 / 越满扣线红 / 无口径则中性 */
function screenMetricTone(key, v){
  const m = SCREEN_METRICS.find(x => x.key === key);
  if (!m || v == null) return "dim";
  if (m.normal == null) return "neutral";   // 无判定口径（转速）
  return v >= m.full ? "red" : v >= m.normal ? "yellow" : "green";
}

/** 一台设备上最差的指标状态（卡片色调与 KPI 判定共用；中性不参与） */
function screenWorstMetricTone(eq){
  const t = (state.telemetryMap || {})[eq.equipmentId];
  if (!t) return null;
  let worst = null;
  SCREEN_METRICS.forEach(m => {
    const v = t[m.key];
    if (v == null) return;
    const tone = screenMetricTone(m.key, v);
    if (tone === "red") worst = "red";
    else if (tone === "yellow" && worst !== "red") worst = "yellow";
    else if (tone === "green" && worst == null) worst = "green";
  });
  return worst;
}

function screenEqState(eq){
  const t = (state.telemetryMap || {})[eq.equipmentId];
  const ev = latestEvalOf(eq.equipmentId);
  let tone = "dim";
  let label = eq.currentStatus ? enumZh("equipmentStatus", eq.currentStatus, eq.currentStatus) : "—";
  if (eq.enabled === false) { tone = "dim"; label = "已停用"; }
  else if (eq.currentStatus === "MAINTAINING") { tone = "red"; }
  else if (eq.currentStatus === "STOPPED") { tone = "dim"; }
  else if (eq.currentStatus === "TRIAL_RUNNING") { tone = "yellow"; }
  else if (eq.currentStatus === "WARNING") { tone = "yellow"; }
  else if (eq.currentStatus === "RUNNING") {
    // 口径（两级，优先权威结论）：
    //   ① 有 B 的评估 → 用评估的风险等级。B 的加权评分已经把四项指标都算进去了，
    //      前端再按单项阈值判一次，就会出现"健康度 94.7 / LOW"却被标黄的自相矛盾。
    //   ② 没有评估（只有 A 的 simulate 会触发 B 评估，多数设备没有）→ 退回实测阈值，
    //      并按"实测越限"措辞，明确这是原始读数而非模型结论。
    if (ev && ev.riskLevel) {
      const r = ev.riskLevel;
      tone = (r === "CRITICAL" || r === "HIGH") ? "red" : (r === "MEDIUM" ? "yellow" : "green");
    } else {
      tone = screenWorstMetricTone(eq) || "green";
      if (tone === "red") label = "未评估 · 实测越限";
      else if (tone === "yellow") label = "未评估 · 指标偏高";
    }
  }
  return { tone: tone, label: label, telemetry: t, ev: ev };
}

function screenEqCard(eq){
  const s = screenEqState(eq);
  const t = s.telemetry;
  let html = '<div class="screen-eq t-' + s.tone + '">'
    + '<div class="screen-eq-hdr">'
    + '<div><span class="mono">' + h(eq.equipmentId) + '</span>'
    + '<div class="mini">' + h(eq.name || "") + '</div></div>'
    + '<span class="pill b-' + s.tone + '">' + h(s.label) + '</span>'
    + '</div><div class="screen-metrics">';
  SCREEN_METRICS.forEach(m => {
    const v = t ? t[m.key] : null;
    const tone = v == null ? "dim" : screenMetricTone(m.key, v);
    const title = m.normal == null ? ' title="额定转速因设备而异，本页不做阈值判定"' : "";
    html += '<div class="screen-metric t-' + tone + '"' + title + '>'
      + '<div class="sm-v">' + h(v == null ? "—" : fmtNum(v, m.dec)) + '</div>'
      + '<div class="sm-l">' + h(m.zh) + '<span class="unit">' + h(m.unit) + '</span></div>'
      + '</div>';
  });
  html += '</div>';
  html += '<div class="screen-eq-foot">'
    + (s.ev
        ? '健康度 <b style="color:' + toneColor(enumTone("riskLevel", s.ev.riskLevel) || "dim")
          + '">' + h(fmtNum(s.ev.healthScore, 1)) + '</b> ' + tag("riskLevel", s.ev.riskLevel)
          + '<span class="mini" style="margin-left:auto;overflow:hidden;text-overflow:ellipsis;'
          + 'white-space:nowrap;max-width:150px">' + h(s.ev.suspectedFault || "") + '</span>'
        : '<span class="mini">尚无健康评估记录</span>')
    + '</div></div>';
  return html;
}

function screenEqGridHtml(){
  const eqs = (state.equipment || []).slice().sort((a, b) =>
    String(a.equipmentId).localeCompare(String(b.equipmentId)));
  return '<div class="screen-grid" id="screen-grid">' + eqs.map(screenEqCard).join("") + '</div>';
}

function screenBody(){
  const eqs = state.equipment || [];
  const warns = activeWarnings();
  const bad   = eqs.filter(e => screenEqState(e).tone === "red");
  const mid   = eqs.filter(e => screenEqState(e).tone === "yellow");
  const ok    = eqs.filter(e => screenEqState(e).tone === "green");

  let html = '<div class="screen-hdr">'
    + '<div><div class="screen-title">实时监控大屏</div>'
    + '<div class="mini">全厂 ' + eqs.length + ' 台关键设备 · 遥测与健康状态 · 每 '
    + Math.round(REFRESH_MS / 1000) + ' 秒轮询</div></div>'
    + '<div class="screen-clock mono" id="screen-clock">'
    + h(new Date().toLocaleString("zh-CN")) + '</div>'
    + '</div>';

  html += noticeInfo("阈值取色口径与 B 服务 <span class=\"mono\">scoring.py</span> 一致："
    + "振动 3.0/6.0 <span class=\"mono\">mm·s⁻¹</span>、温度 70/90 ℃、电流 15/30 A。"
    + "<br>两处颜色含义不同：<b>指标格</b>是单项原始读数对照阈值（黄＝已进入扣分区间，"
    + "红＝达到满扣线）；<b>卡片边框与右上徽标</b>是综合结论——有 B 评估时用评估的风险等级"
    + "（B 的加权评分已把四项都算进去），没有评估的才退回实测阈值并标「未评估」。"
    + "所以「单项已泛黄、综合仍为低风险」不矛盾。"
    + "<br><b>转速刻意不参与取色</b>：额定转速是设备属性，而 A 的 Equipment 模型没有该字段，"
    + "B 的 <span class=\"mono\">NOMINAL_SPEED_RPM=1500</span> 是全局硬编码——"
    + "按它给五号离心泵（2900 rpm）、七号传送带（420 rpm）判红是假警报，"
    + "故本页只中性展示读数（<span class=\"mono\">src/domain/scoring.py:71</span> 已是待修项）。"
    + "<br>A 服务无「批量取全部设备最新遥测」接口，本页逐台并发取最新样点（8 台可行；"
    + "上千台时应新增聚合接口，而非在前端循环请求）。");

  html += '<div class="grid g4 mt">'
    + kpi("green", "正常运行", ok.length, "全部指标在正常区")
    + kpi(mid.length ? "yellow" : "dim", "关注", mid.length, "指标越正常线或试运行")
    + kpi(bad.length ? "red" : "green", "异常", bad.length, bad.length ? "需立即处置" : "无异常设备")
    + kpi("purple", "活跃预警", warns.length, "未闭环预警总数")
    + '</div>';

  html += '<div class="card mt">' + sect("设备实时读数", "按设备编号排序")
    + screenEqGridHtml() + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("需处置设备", bad.length + " 台")
    + table(["设备", "状态", "健康度", "主要问题", "建议"], bad.map(eq => {
        const s = screenEqState(eq);
        return [
          '<span class="mono">' + h(eq.equipmentId) + '</span><div class="mini">'
            + h(eq.name || "") + '</div>',
          '<span class="pill b-red">' + h(s.label) + '</span>',
          s.ev ? '<span style="color:var(--red)">' + h(fmtNum(s.ev.healthScore, 1)) + '</span>'
               : '<span class="mini">—</span>',
          '<span class="mini">' + h((s.ev && s.ev.suspectedFault) || "—") + '</span>',
          '<span class="mini">' + h((s.ev && s.ev.recommendedAction) || "建议立即检修") + '</span>',
        ];
      }), { emptyText: "当前无异常设备", emptyHint: "所有设备指标均在正常区" })
    + '</div>'

    + '<div class="card">' + sect("活跃预警", warns.length + " 条")
    + table(["预警", "设备", "等级", "健康分", "状态"], warns.slice(0, 8).map(w => [
        '<span class="mono mini">' + h(w.warningId) + '</span>',
        '<span class="mono mini">' + h(w.equipmentId) + '</span>',
        tag("riskLevel", w.riskLevel),
        '<span style="color:' + toneColor(enumTone("riskLevel", w.riskLevel) || "dim") + '">'
          + h(fmtNum(w.healthScore, 1)) + '</span>',
        tag("warningStatus", w.status),
      ]), { emptyText: "无活跃预警", emptyHint: "全部预警已闭环" })
    + '</div></div>';

  return html;
}

/** 大屏时钟：只在屏幕页跑，离开时清掉，避免污染其它页面的轮询 */
function startScreenClock(){
  stopScreenClock();
  state.screenClock = setInterval(() => {
    const el = document.getElementById("screen-clock");
    if (!el) { stopScreenClock(); return; }
    el.textContent = new Date().toLocaleString("zh-CN");
  }, 1000);
}
function stopScreenClock(){
  if (state.screenClock) { clearInterval(state.screenClock); state.screenClock = null; }
}

registerPage("screen", {
  async load(ctx){
    if (!state.equipment.length) await loadEquipment();
    // 必须同时拉评估结果与预警：卡片底部要显示健康度/疑似故障，KPI 要数活跃预警。
    // 早期版本只拉了设备与遥测，结果 8 张卡全写着「尚无健康评估记录」。
    await Promise.all([loadLatestEvaluations(), loadWarnings(), loadLatestTelemetry()]);
    startScreenClock();
    return screenBody();
  },
  async poll(ctx){
    if (!document.getElementById("screen-clock")) { stopScreenClock(); return; }
    await Promise.all([loadLatestEvaluations(), loadWarnings(), loadLatestTelemetry()]);
    await refreshCurrent();
  },
});
