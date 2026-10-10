/* ==========================================================================
   data.js —— 共享数据层：一次取数、多页复用
   --------------------------------------------------------------------------
   四个服务的列表接口都被多个页面用到（设备台账/看板/预警/详情都要设备列表）。
   这里做三件事：
     1. 统一取数并写进 state，页面之间共享同一份快照；
     2. 单次请求失败不炸整页——按服务分别降级，页面用 dataStatus 决定怎么提示；
     3. 权限不足（403）与"确实没数据"区分开：前者要告诉用户是权限问题。
   ========================================================================== */
"use strict";

/* 各服务的可用性快照，供页面渲染说明条与空状态时参考 */
state.dataStatus = state.dataStatus || {};

function _mark(svc, ok, err){
  state.dataStatus[svc] = { ok: ok, error: ok ? null : (err || "未知错误"), at: Date.now() };
}

/** 按服务代号取一页数据；失败返回 null 并把原因记进 dataStatus */
async function fetchPage(svc, path){
  try {
    const d = await api(svc, path, { headers: authHeaders() });
    _mark(svc, true);
    return d;
  } catch (e) {
    _mark(svc, false, e.message);
    return null;
  }
}

/** 设备列表（A）。skipHealth 时不动 healthMap */
async function loadEquipment(){
  const d = await fetchPage("a", "/api/v1/equipment?pageSize=100");
  state.equipment = (d && d.items) || [];
  return state.equipment;
}

/** 预警列表（B）+ healthMap 构建。403（无 WARNING_READ）时 warnDenied=true */
async function loadWarnings(){
  state.warnDenied = false;
  try {
    const d = await api("b", "/api/v1/warnings?pageSize=100", { headers: authHeaders() });
    _mark("b", true);
    state.warnings = d.items || [];
  } catch (e) {
    state.warnings = [];
    // 403 是权限问题，不是服务故障——分开表达，否则用户会去查服务
    state.warnDenied = /权限|403|forbidden/i.test(e.message);
    if (!state.warnDenied) _mark("b", false, e.message);
  }
  rebuildHealthMap();
  return state.warnings;
}

/** 从预警列表构建设备健康快照（最新一条预警代表该设备当前风险） */
function rebuildHealthMap(){
  state.healthMap = {};
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
}

/** 用 B 的最新评估覆盖 healthMap（评估比预警新，代表"现在的健康"） */
async function loadLatestEvaluations(){
  const eqs = state.equipment || [];
  await Promise.all(eqs.map(async eq => {
    try {
      const latest = await api("b", "/api/v1/health-evaluations/latest?equipmentId="
        + encodeURIComponent(eq.equipmentId), { headers: authHeaders() });
      if (latest && latest.hasEvaluation) {
        state.latestEvaluation[eq.equipmentId] = latest;
        state.healthMap[eq.equipmentId] = {
          score: latest.healthScore, riskLevel: latest.riskLevel,
          fault: latest.suspectedFault, action: latest.recommendedAction,
          warningId: null, status: isHealthy(latest) ? "RESOLVED" : "OPEN",
          _t: Date.now(),
        };
      }
    } catch (e) { /* 单台失败不影响其它 */ }
  }));
}

/** 每台设备的最新一条遥测（pageSize=1，接口按 measuredAt 倒序）。
 *  驾驶舱/台账的"振动/温度"列需要它——没有批量遥测接口，所以按台并发取。 */
async function loadLatestTelemetry(){
  const eqs = state.equipment || [];
  state.telemetryMap = state.telemetryMap || {};
  await Promise.all(eqs.map(async eq => {
    try {
      const d = await api("a", "/api/v1/equipment/" + encodeURIComponent(eq.equipmentId)
        + "/telemetry?pageSize=1", { headers: authHeaders() });
      const items = d.items || [];
      state.telemetryMap[eq.equipmentId] = items.length ? items[0] : null;
    } catch (e) { state.telemetryMap[eq.equipmentId] = null; }
  }));
}

/** 某设备当前的健康快照（最新评估优先，其次最新预警，再次 healthMap） */
function latestEvalOf(eqId){
  return state.latestEvaluation[eqId] || state.healthMap[eqId] || null;
}

/** 当前活跃（未闭环）的预警 */
function activeWarnings(){
  return (state.warnings || []).filter(w =>
    ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER"].includes(w.status));
}

/** 未结工单（未完成且未取消） */
function openOrders(){
  return (state.orders || []).filter(o => !["COMPLETED","CANCELLED"].includes(o.status));
}

/** 该评估是否表示设备处于健康状态 */
function isHealthy(ev){
  if (!ev) return false;
  if (ev.riskLevel === "LOW") return true;
  return Number(ev.healthScore) >= 80;
}

/** 工单列表（C） */
async function loadOrders(){
  const d = await fetchPage("c", "/api/v1/work-orders?pageSize=100");
  state.orders = (d && d.items) || [];
  return state.orders;
}

/** 备件列表（C） */
async function loadSpareParts(){
  const d = await fetchPage("c", "/api/v1/spare-parts?pageSize=100");
  state.spareParts = (d && d.items) || [];
  return state.spareParts;
}

/** 评估历史（B），供健康中心与设备详情用 */
async function loadEvaluations(query){
  const d = await fetchPage("b", "/api/v1/health-evaluations?pageSize=100" + (query || ""));
  return (d && d.items) || [];
}

/** 核心三件套（设备 + 预警 + 工单）——多数页面进入时都要 */
async function loadCore(){
  await loadEquipment();
  await Promise.all([loadWarnings(), loadOrders()]);
  await Promise.all([loadLatestEvaluations(), loadLatestTelemetry()]);
  if (typeof refreshNavBadges === "function") refreshNavBadges();
}

/** 一键演示：注入异常 → 预警 → 自动建单（顶栏按钮） */
async function runDemo(){
  const eq = (state.equipment || []).find(e => e.enabled !== false);
  if (!eq) { toast("没有可用设备，无法演示", "err"); return; }
  const yes = await confirmBox("一键演示全链路",
    "将对设备 <b>" + h(eq.equipmentId) + " " + h(eq.name) + "</b> 注入一次异常遥测：<br><br>"
    + '<span class="mono">A</span> 写入异常样点（96.7℃ / 9.8 mm·s⁻¹）→ '
    + '<span class="mono">B</span> 健康评分并创建预警 → '
    + '<span class="mono">C</span> 按预警自动建工单 → '
    + '<span class="mono">D</span> 下发通知<br><br>'
    + "全程走真实接口，可在「系统集成监控」页看到事件投递记录。",
    { okText: "开始演示" });
  if (!yes) return;
  await injectData("abnormal", eq.equipmentId);
}
