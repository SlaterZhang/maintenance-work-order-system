/* 预警中心 —— 全厂预警台账：确认 / 转工单 / 闭环追溯
   真实接口：B GET /api/v1/warnings、GET /api/v1/warnings/{id}、
             POST /api/v1/warnings/{id}/acknowledgements（确认） */
"use strict";

registerPage("warns", {
  async load(ctx){
    await loadCore();
    state.warnTab = state.warnTab || "all";
    return null;
  },
  render(){ return pageHdr("预警中心", "全厂预警台账 · 确认 · 转工单 · 闭环追溯", warnsToolbar()) + warnsBody(); },
  after(){
    // 从 #/warn/<id> 进来时自动展开该条
    const r = parseHash();
    if (r.params && r.params.warningId) showWarningDetail(r.params.warningId);
  },
  async poll(){ if (document.getElementById("warn-tbl")) { await loadCore(); await refreshWarnsArea(); } },
});

function warnsToolbar(){
  return '<button class="btn btn-ghost btn-sm" onclick="exportWarnsCsv()">⇩ 导出</button>'
    + '<button class="btn btn-sm" onclick="refreshCurrent()">↻ 刷新</button>';
}

/** Tab 过滤：全部 / 活跃 / 已闭环 */
function warnFiltered(){
  const tab = state.warnTab || "all";
  let list = state.warnings || [];
  if (tab === "active") list = list.filter(w => ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER"].includes(w.status));
  else if (tab === "closed") list = list.filter(w => ["RESOLVED","FALSE_POSITIVE","CANCELLED"].includes(w.status));
  return list;
}

function warnsBody(){
  const all = state.warnings || [];
  const active = activeWarnings();
  const closed = all.filter(w => ["RESOLVED","FALSE_POSITIVE","CANCELLED"].includes(w.status));
  const denied = state.warnDenied;

  if (denied) {
    return noticeWarn("当前账号无 <span class=\"mono\">WARNING_READ</span> 权限，预警列表不可见。"
        + "可在「组织与权限」页查看本账号的权限清单，或改用系统管理员 USER-D-001 登录。")
      + '<div class="card mt">' + emptyBox("权限不足以读取预警", "B 服务对 /api/v1/warnings 做了服务端强制鉴权") + '</div>';
  }

  let html = noticeLive("数据来源：真实接口 — B <span class=\"mono\">GET /api/v1/warnings</span>、"
    + "<span class=\"mono\">POST /warnings/{id}/acknowledgements</span>（确认）。"
    + "预警状态机：OPEN → ACKNOWLEDGED → LINKED_TO_ORDER → RESOLVED，另有终态 FALSE_POSITIVE（误报）与 CANCELLED（工单取消回流）。");

  const byRisk = {};
  active.forEach(w => { byRisk[w.riskLevel] = (byRisk[w.riskLevel] || 0) + 1; });
  const acked = all.filter(w => w.acknowledgedAt);
  const avgAck = acked.length
    ? Math.round(acked.reduce((s, w) =>
        s + (new Date(w.acknowledgedAt) - new Date(w.warningAt)) / 60000, 0) / acked.length)
    : null;
  const linkedTo = all.filter(w => w.linkedOrderId).length;

  html += '<div class="grid g5 mt">'
    + kpi("bad", "严重 CRITICAL", byRisk.CRITICAL || 0, "需立即处置")
    + kpi("warn", "高 HIGH", byRisk.HIGH || 0, "24h 内安排")
    + kpi("cyan", "活跃预警", active.length, "待处理 + 已确认 + 已建单")
    + kpi("ok", "已闭环", closed.length, all.length + " 条历史")
    + kpi("purple", "平均确认时长", avgAck === null ? "—" : (avgAck + " min"),
        avgAck === null ? "暂无确认记录" : "目标 &lt;60")
    + '</div>';

  // ---- 筛选 + 表格 ----
  html += '<div class="card mt">'
    + '<div class="li" style="gap:8px;flex-wrap:wrap;margin-bottom:10px">'
    + '<div class="tabs" style="margin:0">'
    + ["all", "active", "closed"].map((t, i) =>
        '<button class="' + (state.warnTab === t ? "on" : "")
        + '" onclick="setWarnTab(\'' + t + '\')">'
        + ({all:"全部", active:"活跃", closed:"已闭环"})[t]
        + '</button>').join("")
    + '</div>'
    + '<span class="spacer" style="flex:1"></span>'
    + '<span class="mini">共 ' + warnFiltered().length + ' 条</span></div>'
    + '<div id="warn-tbl">' + warnTableHtml() + '</div>'
    + '</div>';

  // ---- 状态机 + 统计 ----
  html += '<div class="grid g-2-1 mt">';
  html += '<div class="card">' + sect("预警状态机", "6 态")
    + '<div class="li" style="gap:10px;flex-wrap:wrap;margin-bottom:12px">'
    + ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER","RESOLVED","FALSE_POSITIVE","CANCELLED"]
        .map(s => tag("warningStatus", s)).join(" ")
    + '</div>'
    + '<table><tbody>'
    + '<tr><td style="width:150px">' + statusDot("warningStatus","OPEN") + '待处理</td>'
    + '<td class="mini">评估判定为 HIGH / CRITICAL（可处置风险）时创建，并尝试推送工单</td></tr>'
    + '<tr><td>' + statusDot("warningStatus","ACKNOWLEDGED") + '已确认</td>'
    + '<td class="mini">人工确认收到，记录确认人与时间</td></tr>'
    + '<tr><td>' + statusDot("warningStatus","LINKED_TO_ORDER") + '已转工单</td>'
    + '<td class="mini">C 服务建单成功后回填 linkedOrderId（由 outbox 事件驱动）</td></tr>'
    + '<tr><td>' + statusDot("warningStatus","RESOLVED") + '已闭环</td>'
    + '<td class="mini">两条路径：① 维修结论 RECOVERED（C-INT-05）；'
    + '② 设备恢复正常自动闭环（评估 LOW 时 AUTO_RESOLVE）</td></tr>'
    + '<tr><td>' + statusDot("warningStatus","FALSE_POSITIVE") + '误报 / 已取消</td>'
    + '<td class="mini">误报标记；或工单取消时由 OrderCancelledReported（C-INT-08）回流置为 CANCELLED</td></tr>'
    + '</tbody></table></div>';

  html += '<div class="card">' + sect("按故障类型 TOP 5", "近 30 天")
    + bars(faultTop(all), "cyan", " 次") + '</div>';
  html += '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("按设备 TOP 5", "预警次数")
    + bars(eqTop(all), "yellow", " 次") + '</div>'
    + '<div class="card">' + sect("近 14 天预警趋势", "按天新增")
    + spark(dailyCounts(all, 14), toneColor("bad"), {w: 520, h: 90}) + '</div>'
    + '</div>';

  return html;
}

function warnTableHtml(){
  const list = warnFiltered();
  if (!list.length) return emptyBox("暂无预警记录",
    "可到「设备详情」页用注入工作台制造一条：注入异常数据 → A 写入遥测 → B 评估建预警 → C 自动建单");

  const rows = list.map(w => {
    const eq = (state.equipment || []).find(e => e.equipmentId === w.equipmentId);
    const canAck = w.status === "OPEN";
    const ops = '<button class="btn btn-ghost btn-sm" onclick="showWarningDetail(\''
      + h(w.warningId) + '\')">详情</button>'
      + (canAck ? ' <button class="btn btn-sm" onclick="acknowledgeWarning(\''
          + h(w.warningId) + '\')">确认</button>' : "");
    return [
      '<span class="mono">' + h(w.warningId) + '</span>',
      h(w.equipmentId) + (eq ? ' <span class="mini">' + h(eq.name) + '</span>' : ""),
      tag("riskLevel", w.riskLevel),
      '<span style="color:' + toneColor(w.healthScore >= 80 ? "ok" : w.healthScore >= 60 ? "warn" : "bad")
        + ';font-weight:600">' + fmtNum(w.healthScore, 1) + '</span>',
      h(w.suspectedFault),
      tag("warningStatus", w.status),
      w.linkedOrderId
        ? '<a class="mono" style="color:var(--cyan);cursor:pointer" onclick="navigate(\'order/'
            + h(w.linkedOrderId) + '\')">' + h(w.linkedOrderId) + '</a>'
        : '<span class="mini">—</span>',
      '<span class="mini">' + fmtTime(w.warningAt) + '</span>',
      ops,
    ];
  });
  return table(["预警编号","设备","等级","健康分","疑似故障","状态","关联工单","时间","操作"], rows);
}

/** 故障类型 TOP（LOW 的"未见明显异常特征"不算故障） */
function faultTop(list){
  const m = {};
  list.forEach(w => {
    if (!w.suspectedFault || w.suspectedFault === "未见明显异常特征") return;
    m[w.suspectedFault] = (m[w.suspectedFault] || 0) + 1;
  });
  return Object.keys(m).sort((a, b) => m[b] - m[a]).slice(0, 5)
    .map(k => ({ label: k, value: m[k] }));
}
function eqTop(list){
  const m = {};
  list.forEach(w => { m[w.equipmentId] = (m[w.equipmentId] || 0) + 1; });
  return Object.keys(m).sort((a, b) => m[b] - m[a]).slice(0, 5)
    .map(k => {
      const eq = (state.equipment || []).find(e => e.equipmentId === k);
      return { label: k + (eq ? " · " + eq.name : ""), value: m[k] };
    });
}
/** 近 n 天每日新增条数 */
function dailyCounts(list, n){
  const days = [], now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 86400000);
    days.push(d.toISOString().slice(0, 10));
  }
  const m = {};
  days.forEach(d => { m[d] = 0; });
  list.forEach(w => {
    const d = String(w.warningAt || "").slice(0, 10);
    if (d in m) m[d]++;
  });
  return days.map(d => m[d]);
}

function setWarnTab(t){
  state.warnTab = t;
  route(true);
}

/** 只刷新预警区（轮询用，避免整页重渲染冲掉用户操作） */
async function refreshWarnsArea(){
  const el = document.getElementById("warn-tbl");
  if (el) el.innerHTML = warnTableHtml();
}

/** 预警详情弹窗：显示契约字段 + 关联工单 + 建议措施 */
function showWarningDetail(warningId){
  const w = (state.warnings || []).find(x => x.warningId === warningId);
  if (!w) { alertBox("未找到预警", "预警 " + h(warningId) + " 不在当前快照中，请点刷新。"); return; }
  const eq = (state.equipment || []).find(e => e.equipmentId === w.equipmentId);
  let html = '<table><tbody>'
    + '<tr><td style="width:120px">预警编号</td><td class="mono">' + h(w.warningId) + '</td></tr>'
    + '<tr><td>设备</td><td>' + h(w.equipmentId) + (eq ? " · " + h(eq.name) : "") + '</td></tr>'
    + '<tr><td>风险等级</td><td>' + tag("riskLevel", w.riskLevel) + '</td></tr>'
    + '<tr><td>健康分</td><td>' + fmtNum(w.healthScore, 1) + ' / 100</td></tr>'
    + '<tr><td>疑似故障</td><td>' + h(w.suspectedFault) + '</td></tr>'
    + '<tr><td>建议措施</td><td>' + h(w.recommendedAction) + '</td></tr>'
    + '<tr><td>状态</td><td>' + tag("warningStatus", w.status) + '</td></tr>'
    + '<tr><td>评分模型</td><td class="mono">' + h(w.modelVersion) + '</td></tr>'
    + '<tr><td>发生时间</td><td>' + fmtTimeSec(w.warningAt) + '</td></tr>'
    + '<tr><td>确认人</td><td>' + (w.acknowledgedBy ? h(w.acknowledgedBy) : '<span class="mini">未确认</span>') + '</td></tr>'
    + '<tr><td>确认时间</td><td>' + (w.acknowledgedAt ? fmtTimeSec(w.acknowledgedAt) : '<span class="mini">—</span>') + '</td></tr>'
    + '<tr><td>关联工单</td><td>' + (w.linkedOrderId
        ? '<a class="mono" style="color:var(--cyan);cursor:pointer" onclick="closeAllModals();navigate(\'order/'
          + h(w.linkedOrderId) + '\')">' + h(w.linkedOrderId) + '</a>'
        : '<span class="mini">未转工单</span>') + '</td></tr>'
    + '<tr><td>乐观锁版本</td><td class="mono">v' + h(w.version) + '</td></tr>'
    + '</tbody></table>';
  if (w.status === "OPEN") {
    html += '<div class="mt" style="display:flex;gap:8px">'
      + '<button class="btn" onclick="closeAllModals();acknowledgeWarning(\'' + h(w.warningId) + '\')">确认收到</button>'
      + '</div>';
  }
  openModal("预警详情 · " + w.warningId, html, {width: 640});
}

/** 确认预警：POST /warnings/{id}/acknowledgements（需 WARNING_ACKNOWLEDGE 权限） */
async function acknowledgeWarning(warningId){
  const w = (state.warnings || []).find(x => x.warningId === warningId);
  if (!w) return;
  if (!(state.user && state.user.userId)) { toast("请先登录", "err"); return; }
  log("确认预警", warningId + "（expectedVersion=" + w.version + "）", true);
  try {
    await api("b", "/api/v1/warnings/" + encodeURIComponent(warningId) + "/acknowledgements", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        operatorId: state.user.userId,
        expectedVersion: w.version,
        comment: "界面确认",
      }),
    });
    toast("预警 " + warningId + " 已确认", "ok");
    log("确认成功", warningId, true);
    await loadWarnings();
    await route(true);
  } catch (e) {
    toast("确认失败：" + e.message, "err");
    log("确认失败", e.message, false);
  }
}

function exportWarnsCsv(){
  const list = warnFiltered();
  if (!list.length) { toast("没有可导出的预警", "err"); return; }
  const head = ["预警编号","设备","等级","健康分","疑似故障","状态","关联工单","时间"];
  const rows = list.map(w => [w.warningId, w.equipmentId, w.riskLevel, w.healthScore,
    w.suspectedFault, w.status, w.linkedOrderId || "", w.warningAt]);
  downloadCsv("预警台账", head, rows);
}
