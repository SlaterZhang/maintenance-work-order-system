/* 健康评估中心 —— 全厂健康评分 · 风险分级 · 评估历史追溯
   真实接口：B GET /api/v1/health-evaluations（历史）、
             GET /api/v1/health-evaluations/latest?equipmentId=（最新，本次新增） */
"use strict";

registerPage("health", {
  async load(){ await loadCore(); await loadHealthHistory(); return null; },
  render(){ return pageHdr("健康评估中心", "全厂健康评分 · 风险分级 · 评估历史追溯", healthToolbar())
    + healthBody(); },
  async poll(){ if (document.getElementById("health-hist")) { await loadCore(); await refreshHealthArea(); } },
});

function healthToolbar(){
  return '<button class="btn btn-ghost btn-sm" onclick="exportHealthCsv()">⇩ 导出评估报告</button>'
    + '<button class="btn btn-sm" onclick="refreshCurrent()">↻ 刷新</button>';
}

function healthBody(){
  const eqs = state.equipment || [];
  const evals = state.healthHistory || [];
  const scored = eqs.filter(e => latestEvalOf(e.equipmentId));

  let html = noticeLive("数据来源：真实接口 — B <span class=\"mono\">GET /api/v1/health-evaluations</span>"
    + "（历史，本次新增的只读查询）与 <span class=\"mono\">/latest?equipmentId=</span>（最新快照）。"
    + "评估由 A 的 <span class=\"mono\">simulate</span> 注入触发：A 写入遥测 → 调 B 评估 → 落库 health_evaluation 表。");

  // ---- KPI ----
  const today = new Date().toISOString().slice(0, 10);
  const todayCnt = evals.filter(e => String(e.evaluatedAt || "").slice(0, 10) === today).length;
  const low = scored.filter(e => latestEvalOf(e.equipmentId).riskLevel === "LOW").length;
  const mid = scored.filter(e => latestEvalOf(e.equipmentId).riskLevel === "MEDIUM").length;
  const high = scored.filter(e => {
    const r = latestEvalOf(e.equipmentId).riskLevel;
    return r === "HIGH" || r === "CRITICAL";
  }).length;
  const avg = scored.length
    ? scored.reduce((s, e) => s + Number(latestEvalOf(e.equipmentId).healthScore || 0), 0) / scored.length
    : null;

  html += '<div class="grid g5 mt">'
    + kpi("cyan", "今日评估", todayCnt, "累计 " + evals.length + " 条")
    + kpi("ok", "LOW（正常）", low, "占比 " + (scored.length ? Math.round(low / scored.length * 100) : 0) + "%")
    + kpi("warn", "MEDIUM（关注）", mid, "仅记录，不建预警")
    + kpi("bad", "HIGH / CRITICAL", high, "已建单 " + (state.warnings || []).filter(w => w.riskLevel === "HIGH" || w.riskLevel === "CRITICAL").length + " 张")
    + kpi("purple", "平均健康分", avg === null ? "—" : fmtNum(avg, 1), "阈值 80 / 60")
    + '</div>';

  // ---- 全厂健康度总览 + 风险分布 ----
  html += '<div class="grid g-2-1 mt">';
  html += '<div class="card">' + sect("全厂健康度总览", eqs.length + " 台设备")
    + '<div class="grid g4">'
    + eqs.map(e => {
        const ev = latestEvalOf(e.equipmentId);
        const sc = ev ? Number(ev.healthScore) : null;
        const tone = sc === null ? "dim" : sc >= 80 ? "ok" : sc >= 60 ? "warn" : "bad";
        const col = toneColor(tone);
        return '<div style="text-align:center;padding:6px">'
          + donut(sc === null ? 0 : sc, col, 92, sc === null ? "—" : fmtNum(sc, 0))
          + '<div class="mini mono" style="margin-top:6px">' + h(e.equipmentId) + '</div>'
          + '<div class="mini" style="height:32px;overflow:hidden">' + h(e.name || "") + '</div>'
          + '<div style="margin-top:4px">' + (ev ? tag("riskLevel", ev.riskLevel)
              : '<span class="pill b-dim">未评估</span>') + '</div></div>';
      }).join("")
    + '</div></div>';

  const riskCount = {};
  scored.forEach(e => {
    const r = latestEvalOf(e.equipmentId).riskLevel;
    riskCount[r] = (riskCount[r] || 0) + 1;
  });
  html += '<div class="card">' + sect("风险等级分布", scored.length + " 台已评估")
    + bars(["LOW","MEDIUM","HIGH","CRITICAL"].map(r => ({
        label: enumZh("riskLevel", r), value: riskCount[r] || 0, tone: enumTone("riskLevel", r),
        sub: ({LOW:"≥80 自动闭环", MEDIUM:"60-79 关注", HIGH:"40-59 建单", CRITICAL:"&lt;40 紧急"})[r],
      })), null, " 台")
    + '</div></div>';

  // ---- 评分算法说明 ----
  html += '<div class="card mt">' + sect("健康分算法说明", "可复算")
    + '<div class="mini" style="line-height:1.9;margin-bottom:10px">'
    + '分数从 100 起扣：<span class="mono">ratio = (value - normal) / (full - normal)</span>，'
    + '<span class="mono">score = 100 - Σ(weight × clamp(ratio, 0, 1))</span>。'
    + '任一指标进入报警区（ratio ≥ 1）健康分不高于 <b>59.9</b>，进入跳闸区（ratio ≥ 1.5）不高于 <b>39.9</b>'
    + '——避免单项严重异常被加权平均稀释。定义在 '
    + '<span class="mono">apps/fault-warning/src/domain/scoring.py</span>。</div>'
    + table(["指标","单位","正常","满扣","权重","疑似故障来源"], [
        ["振动速度","mm·s⁻¹","3.0","6.0","40%","主轴轴承振动异常"],
        ["轴承温度","℃","70","90","25%","设备温升异常"],
        ["运行电流","A","15","30","20%","驱动电流异常"],
        ["转速偏离","%（相对额定）","5%","15%","15%","转速偏差异常"],
      ])
    + '<div class="mini" style="margin-top:8px">阈值参考 ISO 20816-1:2016（前身 ISO 10816）'
    + '振动烈度分区，取更保守的 3.0 / 6.0 mm·s⁻¹ 作为教学演示阈值；转速按相对额定 1500 rpm 的偏离比例衡量。</div>'
    + '</div>';

  // ---- 趋势 ----
  html += '<div class="grid g2 mt">';
  html += '<div class="card">' + sect("全厂健康分趋势", "最近 " + evals.length + " 次评估")
    + (evals.length >= 2
        ? spark(evals.slice(0, 40).reverse().map(e => Number(e.healthScore)), toneColor("cyan"), {w: 520, h: 90})
        : emptyBox("评估样本不足", "至少需要 2 次评估才能画趋势"))
    + '<div class="mini" style="margin-top:8px">健康分由 B 服务 rule-engine 计算，'
    + '每条记录都带 <span class="mono">modelVersion</span>，可追溯到是哪个版本算出来的。</div>'
    + '</div>';

  const trendUp = evals.filter(e => e.trend === "RISING").length;
  const trendDown = evals.filter(e => e.trend === "FALLING").length;
  html += '<div class="card">' + sect("指标趋势外推", "增强信息")
    + bars([
        { label:"上行（RISING，恶化）", value: trendUp, tone:"bad" },
        { label:"下行（FALLING，好转）", value: trendDown, tone:"ok" },
        { label:"平稳 / 样本不足（UNKNOWN）", value: evals.length - trendUp - trendDown, tone:"dim" },
      ], null, " 条")
    + '<div class="mini" style="margin-top:10px;line-height:1.8">'
    + '趋势外推是<b>增强信息，绝不阻塞主链路</b>：样本不足或 A 服务不可达时降级为 <span class="mono">UNKNOWN</span>，'
    + '预测字段为 <span class="mono">null</span>——这是本项目一次真实故障的教训。</div>'
    + '</div></div>';

  // ---- 评估历史 ----
  html += '<div class="card mt">'
    + sect("评估历史（全厂）", "最近 " + Math.min(evals.length, 20) + " 条")
    + '<div id="health-hist">' + healthHistoryTableHtml() + '</div></div>';

  return html;
}

function healthHistoryTableHtml(){
  const evals = (state.healthHistory || []).slice(0, 20);
  if (!evals.length) {
    return emptyBox("暂无评估记录",
      "到「设备详情」页用注入工作台点「注入异常数据」，A 会写入遥测并触发 B 评估");
  }
  const rows = evals.map(e => {
    const eq = (state.equipment || []).find(x => x.equipmentId === e.equipmentId);
    return [
      '<span class="mini">' + fmtTimeSec(e.evaluatedAt) + '</span>',
      h(e.equipmentId) + (eq ? ' <span class="mini">' + h(eq.name) + '</span>' : ""),
      '<span style="color:' + toneColor(Number(e.healthScore) >= 80 ? "ok"
        : Number(e.healthScore) >= 60 ? "warn" : "bad") + ';font-weight:600">'
        + fmtNum(e.healthScore, 1) + '</span>',
      tag("riskLevel", e.riskLevel),
      h(e.suspectedFault || "—"),
      e.warningId
        ? '<a class="mono" style="color:var(--cyan);cursor:pointer" onclick="navigate(\'warn/'
            + h(e.warningId) + '\')">' + h(e.warningId) + '</a>'
        : '<span class="mini">— 自动闭环</span>',
      '<span class="mono mini">' + h(e.modelVersion || "—") + '</span>',
      '<button class="btn btn-ghost btn-sm" onclick="showEvalDetail(\'' + h(e.evaluationId) + '\')">详情</button>',
    ];
  });
  return table(["时间","设备","健康分","等级","疑似故障","关联预警","模型版本","操作"], rows);
}

async function refreshHealthArea(){
  const el = document.getElementById("health-hist");
  if (el) el.innerHTML = healthHistoryTableHtml();
}

function showEvalDetail(evalId){
  const e = (state.healthHistory || []).find(x => x.evaluationId === evalId);
  if (!e) { alertBox("未找到评估", "请点刷新后重试。"); return; }
  const eq = (state.equipment || []).find(x => x.equipmentId === e.equipmentId);
  let html = '<table><tbody>'
    + '<tr><td style="width:130px">评估编号</td><td class="mono">' + h(e.evaluationId) + '</td></tr>'
    + '<tr><td>设备</td><td>' + h(e.equipmentId) + (eq ? " · " + h(eq.name) : "") + '</td></tr>'
    + '<tr><td>健康分</td><td>' + fmtNum(e.healthScore, 1) + ' / 100</td></tr>'
    + '<tr><td>风险等级</td><td>' + tag("riskLevel", e.riskLevel) + '</td></tr>'
    + '<tr><td>疑似故障</td><td>' + h(e.suspectedFault || "—") + '</td></tr>'
    + '<tr><td>建议措施</td><td>' + h(e.recommendedAction || "—") + '</td></tr>'
    + '<tr><td>评分模型</td><td class="mono">' + h(e.modelVersion || "—") + '</td></tr>'
    + '<tr><td>趋势</td><td>' + h(trendConclusionZh(e)) + '</td></tr>'
    + '<tr><td>评估时间</td><td>' + fmtTimeSec(e.evaluatedAt) + '</td></tr>'
    + '<tr><td>关联预警</td><td>' + (e.warningId ? '<span class="mono">' + h(e.warningId) + '</span>'
        : '<span class="mini">无（LOW 不建预警）</span>') + '</td></tr>'
    + '</tbody></table>';
  openModal("评估详情 · " + e.evaluationId, html, {width: 620});
}

function exportHealthCsv(){
  const evals = state.healthHistory || [];
  if (!evals.length) { toast("没有可导出的评估记录", "err"); return; }
  downloadCsv("health-evaluations",
    ["时间","设备","健康分","等级","疑似故障","建议措施","关联预警","模型版本"],
    evals.map(e => [e.evaluatedAt, e.equipmentId, e.healthScore, e.riskLevel,
      e.suspectedFault, e.recommendedAction, e.warningId || "", e.modelVersion]));
}
