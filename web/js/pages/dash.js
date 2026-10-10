/* 驾驶舱首页：全厂态势一屏掌握。真实接口：A 设备 / B 预警+评估 / C 工单 */
"use strict";

/** 设备运行状态灯：真实状态优先，再看健康评估（维修中必是红灯） */
function equipmentLight(eq){
  if (eq.currentStatus === "MAINTAINING") return "bad";
  if (eq.currentStatus === "STOPPED") return "dim";
  if (eq.currentStatus === "TRIAL_RUNNING") return "warn";
  const latest = state.latestEvaluation[eq.equipmentId] || state.healthMap[eq.equipmentId];
  if (latest) {
    if (latest.status === "RESOLVED" || latest.status === "CLOSED") return "ok";
    const s = Number(latest.score);
    if (Number.isFinite(s) && (s >= 80 || latest.riskLevel === "LOW")) return "ok";
    if (Number.isFinite(s) && s >= 60) return "warn";
    return "bad";
  }
  return "ok";
}
function lightColor(l){ return toneColor(l); }

/** 首页用到的统计口径，集中在一处，避免各卡片各算一套 */
function dashStats(){
  const eqs = state.equipment || [], ws = state.warnings || [], os = state.orders || [];
  let ok = 0, warn = 0, bad = 0;
  for (const eq of eqs) {
    const l = equipmentLight(eq);
    if (l === "ok") ok++; else if (l === "warn") warn++; else if (l === "bad") bad++;
  }
  const active = ws.filter(w => ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER"].includes(w.status));
  const openOrders = os.filter(o => !["COMPLETED","CANCELLED"].includes(o.status));
  const maintaining = eqs.filter(e => e.currentStatus === "MAINTAINING");
  // 健康度分布：健康(>=80) / 关注(60-79) / 异常(<60)
  // 三档之外单列 unknown：把"没评估过"混进"健康"会让环形图虚高成 100%（曾如此）
  const dist = { healthy:[], watch:[], bad:[], unknown:[] };
  for (const eq of eqs) {
    const hp = state.healthMap[eq.equipmentId];
    const s = hp ? Number(hp.score) : null;
    if (s === null || !Number.isFinite(s)) { dist.unknown.push(eq); continue; }
    if (s >= 80) dist.healthy.push(eq); else if (s >= 60) dist.watch.push(eq); else dist.bad.push(eq);
  }
  const scored = eqs.map(e => state.healthMap[e.equipmentId])
    .filter(x => x && Number.isFinite(Number(x.score))).map(x => Number(x.score));
  const scoredCount = scored.length;
  const avg = scored.length ? scored.reduce((a,b) => a+b, 0) / scored.length : null;
  // 预警分级计数
  const byRisk = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0 };
  for (const w of active) if (byRisk[w.riskLevel] !== undefined) byRisk[w.riskLevel]++;
  return { eqs, active, openOrders, maintaining, dist, avg, scoredCount, byRisk, ok, warn, bad };
}

registerPage("dash", {
  async load(){
    await loadCore();
    return dashHtml();
  },
  async poll(){ await loadCore(); },
});

function dashHtml(){
  const s = dashStats();
  const denied = state.warnDenied;
  const statsErr = state.dataStatus.a && !state.dataStatus.a.ok;

  const hdrRight = '<button class="btn btn-g btn-sm" onclick="navigate(\'screen\')">▣ 实时大屏</button>'
    + '<button class="btn btn-p btn-sm" onclick="refreshCurrent()">↻ 刷新</button>';

  let html = pageHdr("驾驶舱首页", "全厂设备健康态势 · 一屏掌握", hdrRight);

  html += noticeLive(
    "数据来源：<b>真实接口</b> — 设备与状态来自 A <span class='mono'>GET /api/v1/equipment</span>；"
    + "预警与健康评估来自 B <span class='mono'>GET /api/v1/warnings</span> 与 "
    + "<span class='mono'>/health-evaluations/latest</span>；工单来自 C "
    + "<span class='mono'>GET /api/v1/work-orders</span>。本页所有数字均为实时统计。");

  if (statsErr) {
    html += noticeWarn("设备服务（A :8101）当前不可达：" + h(state.dataStatus.a.error)
      + "。请在顶栏「服务地址」检查地址，或确认服务已启动。");
  }

  // ---- KPI ----
  html += '<div class="grid g5 mt">'
    + kpi("cyan", "在管设备", s.eqs.length,
        s.eqs.length ? '<span class="up">4 条产线</span>' : "—")
    + kpi("green", "正常运转", s.ok,
        s.eqs.length ? "占比 " + pct(s.ok, s.eqs.length) + "%" : "—")
    + kpi("red", "活跃预警", s.active.length,
        s.byRisk.CRITICAL ? '<span class="dn">' + s.byRisk.CRITICAL + " 条 CRITICAL</span>" : "无严重预警")
    + kpi("yellow", "维修中", s.maintaining.length,
        s.openOrders.length ? "未结工单 " + s.openOrders.length + " 张" : "无未结工单")
    + kpi("purple", "平均健康度", s.avg === null ? "—" : fmtNum(s.avg, 1),
        '<span class="mini">阈值 80 / 60</span>')
    + '</div>';

  // ---- 健康分布 + 预警分级 ----
  const scoredTotal = s.scoredCount || 0;
  const hp = scoredTotal ? Math.round((s.dist.healthy.length / scoredTotal) * 100) : 0;
  html += '<div class="grid g-2-1 mt">';

  html += '<div class="card">'
    + sect("设备健康度分布", scoredTotal + " / " + s.eqs.length + " 台已评估")
    + '<div class="li" style="gap:22px;align-items:center">'
    + '<div style="flex:0 0 auto">' + donut(hp, toneColor("green"), 118, hp + "%") + '</div>'
    + '<div style="flex:1;min-width:0">'
    + '<div class="li" style="justify-content:space-between;margin-bottom:5px">'
    + '<span class="l1">' + statusDot("riskLevel","LOW") + '健康（≥80）</span>'
    + '<span class="lv">' + s.dist.healthy.length + '</span></div>'
    + '<div class="li" style="justify-content:space-between;margin-bottom:5px">'
    + '<span class="l1">' + statusDot("riskLevel","MEDIUM") + '关注（60–79）</span>'
    + '<span class="lv">' + s.dist.watch.length + '</span></div>'
    + '<div class="li" style="justify-content:space-between">'
    + '<span class="l1">' + statusDot("riskLevel","CRITICAL") + '异常（&lt;60）</span>'
    + '<span class="lv">' + s.dist.bad.length + '</span></div>'
    + (s.dist.unknown.length
        ? '<div class="li" style="justify-content:space-between">'
          + '<span class="l1">' + statusDot("riskLevel","LOW") + '未评估</span>'
          + '<span class="lv">' + s.dist.unknown.length + '</span></div>' : "")
    + '<div class="mini" style="margin-top:10px;line-height:1.6">'
    + '评分口径：4 指标分段线性扣分加权（振动 40% / 温度 25% / 电流 20% / 转速 15%），'
    + '权重与阈值定义在 <span class="mono">apps/fault-warning/src/domain/scoring.py</span>。</div>'
    + '</div></div></div>';

  const riskBars = Object.keys(s.byRisk).map(r => ({
    label: enumZh("riskLevel", r), value: s.byRisk[r],
    tone: enumTone("riskLevel", r),
  }));
  html += '<div class="card">'
    + sect("活跃预警", "按风险等级")
    + (denied
        ? emptyBox("当前角色无预警查看权限（WARNING_READ）",
            "可在「组织与权限」页查看本账号的权限清单")
        : bars(riskBars, null, " 条"))
    + '<div class="mini" style="margin-top:10px">'
    + '预警处置状态：'
    + tag("warningStatus","OPEN") + " " + tag("warningStatus","ACKNOWLEDGED") + " "
    + tag("warningStatus","LINKED_TO_ORDER") + " 属于活跃态。</div>"
    + '</div></div>';

  // ---- 设备实时状态表 ----
  html += '<div class="card mt">'
    + sect("设备实时状态", "点击行进入详情")
    + equipmentTableHtml();
  html += '</div>';

  // ---- 最新预警 ----
  html += '<div class="card mt">'
    + sect("最新预警", "前 8 条")
    + warnTableHtml(8);
  html += '</div>';

  return html;
}

/** 设备状态表：全平台复用（首页 / 台账 / 大屏） */
function equipmentTableHtml(rows){
  const eqs = rows || state.equipment || [];
  if (!eqs.length) {
    return emptyBox("还没有设备数据",
      "确认 A 服务（:8101）已启动；种子数据会在首次启动时自动写入 8 台设备");
  }
  return '<div class="tbl-wrap"><table><thead><tr>'
    + "<th>设备编号</th><th>名称</th><th>位置</th><th>运行状态</th>"
    + "<th>健康度</th><th>振动 mm·s⁻¹</th><th>温度 ℃</th><th>负责人部门</th>"
    + "</tr></thead><tbody>"
    + eqs.map(eq => {
        const hp = state.healthMap[eq.equipmentId];
        const tel = (state.telemetryMap || {})[eq.equipmentId];
        const l = equipmentLight(eq);
        const disabled = eq.enabled === false;
        const score = hp ? Number(hp.score) : null;
        return '<tr class="row-link" onclick="navigate(\'eq/' + h(eq.equipmentId) + '\')"'
          + (disabled ? ' style="opacity:.55"' : '') + '>'
          + '<td><span class="dot d-' + l + '"></span> <b>' + h(eq.equipmentId) + '</b>'
          + (disabled ? ' <span class="pill b-dim">已停用</span>' : '') + '</td>'
          + '<td>' + h(eq.name) + '</td>'
          + '<td class="mini">' + h(eq.productionLineId || "—") + " · " + h(eq.location || "") + '</td>'
          + '<td>' + tag("equipmentStatus", eq.currentStatus) + '</td>'
          + '<td class="mono" style="color:' + (score === null ? "var(--dim)"
              : toneColor(score >= 80 ? "ok" : score >= 60 ? "warn" : "bad")) + '">'
          + (score === null ? "—" : fmtNum(score, 1)) + '</td>'
          + '<td class="mono" style="color:' + (tel && Number(tel.vibrationMmS) >= 3 ? toneColor("bad") : "inherit") + '">'
          + (tel ? fmtMetric(tel.vibrationMmS, 2) : "—") + '</td>'
          + '<td class="mono" style="color:' + (tel && Number(tel.temperatureC) >= 70 ? toneColor("bad") : "inherit") + '">'
          + (tel ? fmtMetric(tel.temperatureC, 1) : "—") + '</td>'
          + '<td class="mini">' + h(eq.responsibleDepartment || "—") + '</td>'
          + '</tr>';
      }).join("")
    + "</tbody></table></div>";
}

/** 预警表：首页 / 预警中心共用 */
function warnTableHtml(limit){
  if (state.warnDenied) {
    return emptyBox("当前角色无预警查看权限（WARNING_READ）",
      "预警列表受权限门禁保护；设备健康状态仍可正常查看");
  }
  const ws = (state.warnings || []).slice(0, limit || 999);
  if (!ws.length) {
    return emptyBox("暂无预警记录",
      "可在「设备详情 → 模拟数据注入工作台」注入一次异常，走通 预警 → 自动建单 全链路");
  }
  return '<div class="tbl-wrap"><table><thead><tr>'
    + "<th>预警编号</th><th>设备</th><th>等级</th><th>健康分</th>"
    + "<th>疑似故障</th><th>状态</th><th>关联工单</th><th>时间</th>"
    + "</tr></thead><tbody>"
    + ws.map(w => '<tr class="row-link" onclick="navigate(\'warn/' + h(w.warningId) + '\')">'
        + '<td class="mono">' + h(w.warningId) + '</td>'
        + '<td>' + h(w.equipmentId) + '</td>'
        + '<td>' + tag("riskLevel", w.riskLevel) + '</td>'
        + '<td class="mono" style="color:' + toneColor(
            Number(w.healthScore) >= 80 ? "ok" : Number(w.healthScore) >= 60 ? "warn" : "bad") + '">'
        + fmtNum(w.healthScore, 1) + '</td>'
        + '<td>' + h(w.suspectedFault || "—") + '</td>'
        + '<td>' + tag("warningStatus", w.status) + '</td>'
        + '<td class="mono">' + (w.linkedOrderId
            ? '<a href="#/order/' + h(w.linkedOrderId) + '">' + h(w.linkedOrderId) + '</a>' : "—") + '</td>'
        + '<td class="mini">' + relTime(w.warningAt) + '</td>'
        + '</tr>').join("")
    + "</tbody></table></div>";
}
