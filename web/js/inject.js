/* ==========================================================================
   inject.js —— 注入工作台 / 停用启用 / 维修后恢复 / 一键演示
   --------------------------------------------------------------------------
   从旧版迁到平台框架：
     * 旧版结尾会调 refreshDashboard()/renderEquipmentList()/openEquipment()/
       refreshEquipmentDetail() —— 这些属于已删除的 dashboard.js / equipment.js，
       现在统一走共享数据层（loadCore）与路由（route(true)）。
     * 去掉了与 data.js 重复的 runDemo()，只保留与工单联动用的恢复函数。
   浏览器不再持 X-Internal-Token 直连内部接口：注入走 A 的授权 simulate 端点，
   预设值由服务端 SIMULATION_PRESETS 统一维护。
   ========================================================================== */
"use strict";

let injectBusy = false;   // 注入进行中：按钮态管理避免与刷新竞态

/* 工作台按钮态：设备停用 → 注入按钮置灰；停用/启用按钮动态切换文案 */
function updateWorkbenchButtons(){
  const btn = $("btn-toggle-enabled");
  if (!btn) return;
  const abn = $("btn-abnormal"), nor = $("btn-normal");
  if (state.eqEnabled === false) {
    btn.textContent = "▶ 启用设备";
    btn.style.background = "#2ecc71";
    btn.title = "恢复主数据在线；设备保持已停止，需注入正常数据恢复运转";
    if (!injectBusy && abn && nor) {
      abn.disabled = true; nor.disabled = true;
      abn.title = nor.title = "设备已停用，遥测注入被拒绝（409），请先启用设备";
      const hint = $("inject-hint");
      if (hint) hint.textContent = "设备已停用：遥测注入被拒绝（409 EQUIPMENT_DISABLED），请先启用设备";
    }
  } else {
    btn.textContent = "⛔ 停用设备";
    btn.style.background = "#6b7a94";
    btn.title = "主数据级下线：停用后拒绝遥测注入，启用后需注入正常数据恢复运转";
    if (!injectBusy && abn && nor) {
      abn.disabled = false; nor.disabled = false;
      abn.title = nor.title = "";
    }
  }
}

/* 停用/启用设备（主数据级下线）：
   停用 = enabled=false + 状态联动已停止 + 拒绝遥测（409）；
   启用 = enabled=true，状态不动，需再注入 NORMAL 恢复运转 */
async function toggleEquipmentEnabled(){
  const eqId = state.openEq;
  if (!eqId || injectBusy) return;
  const disable = state.eqEnabled !== false;   // 当前在线 → 停用；已停用 → 启用
  const btn = $("btn-toggle-enabled");
  if (btn) btn.disabled = true;
  try {
    const result = await api("a", `/api/v1/equipment/${eqId}/enabled`, {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body:{enabled: !disable},
    });
    state.eqEnabled = result.enabled;
    if (result.enabled) {
      log("设备启用", `主数据恢复在线，当前状态：${EQ_STATUS_ZH[result.currentStatus] || result.currentStatus}（需注入正常数据恢复运转）`, true);
      toast("设备已启用（状态保持已停止，注入正常数据后恢复运转）", "ok");
    } else {
      log("设备停用", `主数据下线：${EQ_STATUS_ZH[result.statusBefore] || result.statusBefore} → 已停止，遥测注入将被拒绝（409）`, true);
      toast("设备已停用，遥测注入已禁用", "info");
    }
    await loadCore();
    await route(true);
  } catch (e) {
    log(disable ? "设备停用" : "设备启用", e.message, false);
    toast("操作失败：" + e.message, "err");
  } finally {
    if (btn) btn.disabled = false;
    updateWorkbenchButtons();
  }
}

/* 注入一组预设遥测：A 落库样本 + 服务端联动 B 评估（全链路起点） */
async function injectData(kind, eqIdArg){
  const eqId = eqIdArg || state.openEq;
  if (!eqId) { toast("请先选择设备", "err"); return; }
  const mode = kind === "abnormal" ? "ABNORMAL" : "NORMAL";
  const btnId = kind === "abnormal" ? "btn-abnormal" : "btn-normal";
  const btn = $(btnId);
  const other = $(kind === "abnormal" ? "btn-normal" : "btn-abnormal");
  const hint = $("inject-hint");
  injectBusy = true;
  if (btn) { btn.disabled = true; btn.textContent = "注入评估中…"; }
  if (other) other.disabled = true;
  if (hint) hint.textContent = "链路执行中：A 存样本 → B 评估 → (B 异步发预警 → C 自动建单)";
  showStatus(kind === "abnormal" ? "⚠️ 正在注入异常数据..." : "✓ 正在恢复数据...");

  try {
    // 授权端点一次完成：A 落库样本 + 服务端联动 B 评估
    const sim = await api("a", `/api/v1/equipment/${encodeURIComponent(eqId)}/simulate`, {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body:{mode},
    });
    const sample = sim.sample;
    log("注入遥测", `A POST simulate（${sample.temperatureC}℃/${sample.vibrationMmS}/${sample.currentA}A）accepted=${sim.ingest.acceptedCount}`, sim.ingest.acceptedCount > 0);

    // 评估失败如实展示（不静默）：数据已落 A，但链路未闭环
    if (sim.evaluationError) {
      log("健康评估", `B 评估失败：${sim.evaluationError}`, false);
      toast("评估失败：" + sim.evaluationError, "err");
      if (hint) hint.textContent = "评估失败：" + sim.evaluationError;
      return;
    }
    const evaluate = sim.evaluation;
    log("健康评估", `B POST health-evaluations → ${evaluate.riskLevel}，健康度 ${evaluate.healthScore}`,
        !!evaluate.riskLevel);
    toast(`评估完成：${evaluate.riskLevel}，健康度 ${evaluate.healthScore}`,
        evaluate.riskLevel === "CRITICAL" || evaluate.riskLevel === "HIGH" ? "err" : "ok");
    if ($("eq-health")) $("eq-health").textContent = evaluate.healthScore;

    // 阶段3：展示退化趋势外推结论（B 基于历史遥测的预测）
    if (evaluate.trend && evaluate.trend !== "UNKNOWN") {
      const concl = trendConclusionZh(evaluate);
      if (concl) {
        log("趋势预测", concl, evaluate.trend === "DEGRADING" ? false : true);
        if (evaluate.trend === "DEGRADING") toast(concl, "err");
      }
    }
    if (evaluate.warningId) {
      log("生成预警", `B 生成预警 ${evaluate.warningId}（${evaluate.suspectedFault}）`, true);
    }
    // 恢复正常数据 = 完全复位：A 已联动把设备状态复位为 RUNNING
    if (kind === "normal" && sim.equipmentStatusRestored) {
      const fromZh = EQ_STATUS_ZH[sim.equipmentStatusRestoredFrom] || sim.equipmentStatusRestoredFrom;
      log("设备状态", `恢复正常数据已联动复位：${fromZh} → 运行中`, true);
    }

    // 等 B→C 异步建单落地，再刷新全链路可见结果
    if (btn) btn.textContent = "等待自动建单…";
    if (hint) hint.textContent = "B 异步发送 WarningRaised → C 自动建单（约 2~5 秒）…";
    await new Promise(r => setTimeout(r, 2500));
    await loadCore();
    await route(true);
    const hint2 = $("inject-hint");
    if (hint2) hint2.textContent = "全链路完成：监测 → 预警 → 建单，可在工单页继续处置";
    log("闭环刷新", "看板/详情/工单列表已刷新（自动建单结果可见）", true);
    showStatus(kind === "abnormal" ? "✅ 异常注入完成！已生成预警和工单" : "✅ 数据已恢复正常");
    setTimeout(hideStatus, 4000);
  } catch (e) {
    hideStatus();
    log(kind === "abnormal" ? "注入异常" : "恢复数据", e.message, false);
    toast("注入链路失败：" + e.message, "err");
    const h3 = $("inject-hint");
    if (h3) h3.textContent = "失败原因：" + e.message;
  } finally {
    injectBusy = false;
    if (btn) {
      btn.textContent = kind === "abnormal" ? "⚡ 注入异常数据" : "☑ 注入正常数据";
      btn.disabled = state.eqEnabled === false;
    }
    if (other) other.disabled = state.eqEnabled === false;
    updateWorkbenchButtons();
  }
}

/* 维修完成后自动恢复：走授权 simulate 端点（服务端联动 B 重评）。
   工单验收通过后由工单页调用；失败不阻断工单流转，只提示可手工恢复。 */
async function recoverEquipmentAfterMaintenance(eqId){
  showStatus("✓ 正在恢复设备状态...");
  try {
    const sim = await api("a", `/api/v1/equipment/${encodeURIComponent(eqId)}/simulate`, {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body:{mode:"NORMAL"},
    });
    if (sim.evaluationError) throw new Error(sim.evaluationError);
    const evaluate = sim.evaluation;
    if (Number(evaluate.healthScore) >= 80 || evaluate.riskLevel === "LOW") {
      state.healthMap[eqId] = {
        score: evaluate.healthScore,
        riskLevel: evaluate.riskLevel,
        fault: evaluate.suspectedFault || "",
        action: evaluate.recommendedAction || "",
        warningId: null,
        status: "RESOLVED",
        _t: Date.now(),
      };
    }
    log("设备恢复", `设备 ${eqId} 已自动恢复正常数据，评估健康度 ${evaluate.healthScore}`, true);
    toast(`✅ 设备已恢复为正常运转状态（健康度 ${evaluate.healthScore}）`, "ok");
    showStatus("✅ 设备已恢复正常");
    setTimeout(hideStatus, 3000);
  } catch (restoreErr) {
    hideStatus();
    log("设备恢复", `自动恢复失败（可手动点击"恢复正常数据"）：${restoreErr.message}`, false);
    toast("⚠️ 工单已完成，但设备恢复失败，请手动恢复", "info");
  }
}
