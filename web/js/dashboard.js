/* 首页看板：统计口径（P2-1）、设备列表、预警列表（P2-9 中文映射） */
"use strict";
/* P2-1 统计口径修正：设备真实状态优先——维修中必是红灯，
   不再被缓存里的旧健康评估盖成黄/绿（"维修中"计数随之准确） */
function equipmentLight(eq){
  if (eq.currentStatus === "MAINTAINING") return "red";
  if (eq.currentStatus === "STOPPED" || eq.currentStatus === "TRIAL_RUNNING") return "gray";
  const latest = state.latestEvaluation[eq.equipmentId] || state.healthMap[eq.equipmentId];
  if (latest) {
    if (latest.status === "RESOLVED" || latest.status === "CLOSED") return "green";
    const s = Number(latest.score);
    if (Number.isFinite(s) && (s > 70 || latest.riskLevel === "LOW" || latest.riskLevel === "NORMAL")) {
      return "green";
    }
    return "yellow";
  }
  return "green";
}

async function refreshDashboard(){
  try {
    const eqPage = await api("a", "/api/v1/equipment?pageSize=100", {headers: authHeaders()});
    state.equipment = eqPage.items || [];
    // 预警列表受 WARNING_READ 门禁：无权限（403）时静默降级，看板统计改走健康评估数据
    state.warnDenied = false;
    try {
      const warnPage = await api("b", "/api/v1/warnings?pageSize=100", {headers: authHeaders()});
      state.warnings = warnPage.items || [];
    } catch (e) {
      state.warnings = [];
      state.warnDenied = true;
    }
    state.healthMap = {};
    // 先从预警列表构建 healthMap
    for (const w of state.warnings) {
      const t = w.warningAt ? new Date(w.warningAt).getTime() : 0;
      const cur = state.healthMap[w.equipmentId];
      if (!cur || t >= cur._t) {
        state.healthMap[w.equipmentId] = {
          score: w.healthScore, riskLevel: w.riskLevel,
          fault: w.suspectedFault, action: w.recommendedAction,
          warningId: w.warningId, status: w.status, _t: t,
        };
      }
    }
    // 从 B 服务获取每个设备的最新健康评估，覆盖预警数据
    const latestPromises = state.equipment.map(async (eq) => {
      try {
        const latest = await api("b", `/api/v1/health-evaluations/latest?equipmentId=${eq.equipmentId}`, {
          headers: authHeaders(),
        });
        if (latest && latest.hasEvaluation) {
          // 健康评估数据优先于预警数据
          state.healthMap[eq.equipmentId] = {
            score: latest.healthScore,
            riskLevel: latest.riskLevel,
            fault: latest.suspectedFault,
            action: latest.recommendedAction,
            warningId: null,
            status: latest.riskLevel === "LOW" || latest.riskLevel === "NORMAL" || latest.healthScore >= 80 ? "RESOLVED" : "OPEN",
            _t: Date.now(),
          };
        }
      } catch (e) {
        console.warn("[refreshDashboard] 获取设备最新评估失败:", eq.equipmentId, e.message);
      }
    });
    await Promise.all(latestPromises);
    let green = 0, warn = 0, fix = 0;
    for (const eq of state.equipment) {
      const light = equipmentLight(eq);
      if (light === "green") green++;
      else if (light === "yellow") warn++;
      else if (light === "red") fix++;
    }
    $("st-total").textContent = state.equipment.length;
    $("st-green").textContent = green;
    $("st-warn").textContent = warn;
    $("st-fix").textContent = fix;
    renderEquipmentList();
    renderWarningList();
    state.lastFetch = Date.now();
  } catch (e) {
    console.error("[refreshDashboard] 数据刷新失败:", e);
    toast("看板数据刷新失败：" + e.message, "err");
  }
}

function renderEquipmentList(){
  const box = $("eq-list"); box.innerHTML = "";
  if (!state.equipment.length) { box.innerHTML = '<div class="empty">无设备数据</div>'; return; }
  for (const eq of state.equipment) {
    const light = equipmentLight(eq);
    const latest = state.latestEvaluation[eq.equipmentId];
    const h = latest || state.healthMap[eq.equipmentId];
    const row = document.createElement("div");
    row.className = "eq-row";
    if (state.openEq === eq.equipmentId) row.classList.add("selected");
    const statusZh = EQ_STATUS_ZH[eq.currentStatus] || eq.currentStatus;
    row.innerHTML =
      `<span class="dot" style="background:${LIGHT_COLOR[light]};box-shadow:0 0 8px ${LIGHT_COLOR[light]}"></span>` +
      `<span><b>${esc(eq.equipmentId)}</b><div class="eq-name">${esc(eq.name)}</div></span>` +
      `<span class="mini">${esc(eq.productionLineId)} · ${esc(statusZh)}</span>` +
      `<span class="health">${h ? esc(h.score) : "--"}</span>` +
      `<span class="mini">健康度</span>`;
    row.onclick = () => openEquipment(eq.equipmentId);
    box.appendChild(row);
  }
}

function renderWarningList(){
  const box = $("warn-list"); box.innerHTML = "";
  if (state.warnDenied) {
    box.innerHTML = '<div class="empty">当前角色无预警查看权限（WARNING_READ）<br>设备健康状态与统计仍实时更新</div>';
    return;
  }
  if (!state.warnings.length) { box.innerHTML = '<div class="empty">暂无预警记录</div>'; return; }
  state.warnings.slice(0, 12).forEach(w => {
    const div = document.createElement("div");
    div.className = "warn-item";
    // P2-9：预警状态带中文映射（括号内保留原枚举便于答辩对照契约）
    const statusZh = WARN_STATUS_ZH[w.status] || w.status;
    div.innerHTML =
      `<div><span class="risk r-${esc(w.riskLevel)}">${esc(w.riskLevel)}</span> ` +
      `<b>${esc(w.equipmentId)}</b> <span class="mini">${esc((w.warningAt || "").replace("T"," ").replace("Z",""))}</span></div>` +
      `<div class="w-fault">${esc(w.suspectedFault)}</div>` +
      `<div class="w-meta">${esc(w.warningId)} · ${esc(statusZh)} · 健康度 ${esc(w.healthScore)}</div>`;
    box.appendChild(div);
  });
}
