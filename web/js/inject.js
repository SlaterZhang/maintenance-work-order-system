/* 注入控制台（第十章演示剧本）、维修后自动恢复、一键演示 */
"use strict";
/* 预设值由 A 服务端统一维护（SIMULATION_PRESETS），浏览器只传 mode，
   不再持 X-Internal-Token 直连内部接口（阶段1鉴权闭合，2026-10-06） */
async function injectData(kind){
  const mode = kind === "abnormal" ? "ABNORMAL" : "NORMAL";
  const btnId = kind === "abnormal" ? "btn-abnormal" : "btn-normal";
  const btn = $(btnId);
  const other = $(kind === "abnormal" ? "btn-normal" : "btn-abnormal");
  btn.disabled = true; other.disabled = true;
  btn.textContent = "注入评估中…";
  $("inject-hint").textContent = "链路执行中：A 存样本 → B 评估 → (B 异步发预警 → C 自动建单)";
  if (kind === 'abnormal') {
    showStatus("⚠️ 正在注入异常数据...");
  } else {
    showStatus("✓ 正在恢复数据...");
  }
  const eqId = state.openEq;
  try {
    // 授权端点一次完成：A 落库样本 + 服务端联动 B 评估
    const sim = await api("a", `/api/v1/equipment/${eqId}/simulate`, {
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
      $("inject-hint").textContent = "评估失败：" + sim.evaluationError;
      return;
    }
    const evaluate = sim.evaluation;
    log("健康评估", `B POST health-evaluations → ${evaluate.riskLevel}，健康度 ${evaluate.healthScore}`,
        evaluate.riskLevel ? true : false);
    toast(`评估完成：${evaluate.riskLevel}，健康度 ${evaluate.healthScore}`,
        evaluate.riskLevel === "CRITICAL" || evaluate.riskLevel === "HIGH" ? "err" : "ok");
    // 立即更新当前页面健康度显示（API缓存可能未同步）
    if ($("eq-health")) {
      $("eq-health").textContent = evaluate.healthScore;
    }
    if (evaluate.warningId) {
      log("生成预警", `B 生成预警 ${evaluate.warningId}（${evaluate.suspectedFault}）`, true);
    }

    // 3) 等待 B→C 异步建单，然后刷新全链路可见结果
    btn.textContent = "等待自动建单…";
    $("inject-hint").textContent = "B 异步发送 WarningRaised → C 自动建单（约 2~5 秒）…";
    await new Promise(r => setTimeout(r, 2500));
    await Promise.all([refreshDashboard(), refreshEquipmentDetail(), loadTelemetry(), refreshOrders()]);
    if (state.view === "equipment") refreshDashboard();
    // 恢复正常：用 B 的最新健康评估结果覆盖该设备 healthMap，清除残留旧预警（30.6→94.7）
    if (evaluate) {
      const ev = {
        score: evaluate.healthScore,
        riskLevel: evaluate.riskLevel,
        fault: evaluate.suspectedFault || "",
        action: evaluate.recommendedAction || "",
        warningId: evaluate.warningId || null,
        status: evaluate.warningId ? "ACTIVE" : "RESOLVED",
        _t: Date.now(),
      };
      // 记录本次注入的评估结果，设备列表优先用它（避免被轮询的旧预警数据覆盖）
      if (!evaluate.warningId) {
        state.latestEvaluation[eqId] = ev;
      } else {
        delete state.latestEvaluation[eqId];
      }
      state.healthMap[eqId] = ev;
      renderEquipmentList();
    }
    log("闭环刷新", "看板/详情/工单列表已刷新（自动建单结果可见）", true);
    $("inject-hint").textContent = "全链路完成：监测 → 预警 → 建单，可在工单页继续处置";
    if (kind === 'abnormal') {
      showStatus("✅ 异常注入完成！已生成预警和工单");
      setTimeout(hideStatus, 4000);
    } else {
      showStatus("✅ 数据已恢复正常");
      setTimeout(hideStatus, 3000);
    }
  } catch (e) {
    hideStatus();
    log(kind === "abnormal" ? "注入异常" : "恢复数据", e.message, false);
    toast("注入链路失败：" + e.message, "err");
    $("inject-hint").textContent = "失败原因：" + e.message;
  } finally {
    btn.disabled = false; other.disabled = false;
    btn.textContent = kind === "abnormal" ? "⚠ 注入异常（严重）" : "✓ 恢复正常数据";
    if (state.openEq) loadTelemetry();
  }
}

/* 维修完成后自动恢复：走授权 simulate 端点（服务端联动 B 重评），
   之前是两段各约 50 行的重复代码直连内部接口（阶段1合并并收口） */
async function recoverEquipmentAfterMaintenance(eqId){
  showStatus("✓ 正在恢复设备状态...");
  try {
    const sim = await api("a", `/api/v1/equipment/${eqId}/simulate`, {
      method:"POST",
      headers: Object.assign(authHeaders(), {"Idempotency-Key": uuidv4()}),
      body:{mode:"NORMAL"},
    });
    if (sim.evaluationError) throw new Error(sim.evaluationError);
    const evaluate = sim.evaluation;
    // 更新前端 healthMap，清除旧预警状态
    if (evaluate.healthScore >= 80 || evaluate.riskLevel === "LOW") {
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

async function runDemo(){
  showStatus("🎬 准备启动演示...");
  log("一键演示", "开始执行全链路演示...", true);
  try {
    if (!state.openEq) {
      showStatus("🔍 查找可用设备...");
      if (!state.equipment.length) await refreshDashboard();
      const eq = state.equipment[0];
      if (eq) {
        showStatus("📱 切换到设备：" + eq.equipmentId);
        await openEquipment(eq.equipmentId);
        log("一键演示", "自动切换至设备详情页：" + eq.equipmentId, true);
      } else {
        hideStatus();
        log("一键演示", "无可用设备，无法注入", false);
        toast("演示失败：未找到可注入的设备", "err");
        return;
      }
    }
    showStatus("⚠️ 注入异常数据...");
    await injectData('abnormal');
    showStatus("⏳ 等待自动建单 (3s)...");
    log("等待联动", "等待 B→C 自动建单 (3s)...", "INFO");
    await new Promise(r=>setTimeout(r,3000));
    showStatus("🔄 刷新页面数据...");
    await refreshDashboard();
    if (state.openEq) { await refreshEquipmentDetail(); await loadTelemetry(true); }
    showStatus("✅ 演示完成！");
    log("一键演示", "演示成功：注入→预警→自动建单 全链路贯通！", true);
    toast("🎉 演示成功！请查看预警和工单列表", "ok");
    setTimeout(hideStatus, 5000);
  } catch (e) {
    hideStatus();
    log("一键演示", "演示失败：" + e.message, false);
    toast("演示失败：" + e.message, "err");
  }
}
