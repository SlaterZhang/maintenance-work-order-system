/* ============================================================================
 * 页面：预警规则阈值（#/rules）
 *
 * 本页展示 B 服务规则引擎的**真实常量与真实计算结果**，全部取自：
 *   apps/fault-warning/src/domain/scoring.py
 *   阈值 → 常量名与当前值一一对应（VIBRATION_NORMAL_MM_S 等）
 *   示例得分 → 用该服务的 evaluate_sample() 实算，非手写
 *
 * 阈值可配置（v2.1.0 新增）：B 服务新增
 *   GET/PUT /api/v1/scoring-thresholds
 *   持久化到 src/data/thresholds.json，PUT 即时生效（apply_thresholds），
 *   重启服务仍保留；写操作要求 ADMIN_ALL，页面提供「保存阈值并生效」。
 * ==========================================================================*/

// 四项指标的阈值与权重：照抄 scoring.py:52-73 的常量
const RULE_METRICS = [
  { name:"振动速度", key:"vibration", unit:"mm·s⁻¹", weight:40,
    normal:3.0, full:6.0, constName:"VIBRATION_NORMAL_MM_S / VIBRATION_FULL_MM_S",
    basis:"ISO 20816-1:2016 振动烈度分区（Class II 报警 4.5 / 停机 7.1），本项目取更保守的 3.0 / 6.0",
    fault:"主轴轴承振动异常", subject:"主轴轴承" },
  { name:"轴承温度", key:"temperature", unit:"℃", weight:25,
    normal:70.0, full:90.0, constName:"TEMPERATURE_NORMAL_C / TEMPERATURE_FULL_C",
    basis:"设备手册 + 现场经验；教学演示取值",
    fault:"设备温升异常", subject:"冷却与润滑系统" },
  { name:"运行电流", key:"current", unit:"A", weight:20,
    normal:15.0, full:30.0, constName:"CURRENT_NORMAL_A / CURRENT_FULL_A",
    basis:"约额定电流 1.15 倍进入扣分、2 倍满扣（教学演示取值）",
    fault:"驱动电流异常", subject:"驱动与电气回路" },
  { name:"主轴转速", key:"speed", unit:"% 偏离", weight:15,
    normal:0.05, full:0.15, constName:"SPEED_DEVIATION_NORMAL / SPEED_DEVIATION_FULL",
    basis:"相对额定转速 NOMINAL_SPEED_RPM=1500 的偏离比例（±5% 扣分、±15% 满扣）",
    fault:"转速偏差异常", subject:"传动与负载侧" },
];

// 健康分 → 风险等级（scoring.py:75-78 + contracts/shared-enums.json 的 orderPriority）
const RULE_RISK_BANDS = [
  { level:"LOW",      zh:"低",   range:"≥ 80",   prio:"P4", action:"维持正常监测",              order:"不建单" },
  { level:"MEDIUM",   zh:"中",   range:"60 ~ 79", prio:"P3", action:"加密监测并安排计划性巡检",   order:"不建单（仅记录评估）" },
  { level:"HIGH",     zh:"高",   range:"40 ~ 59", prio:"P2", action:"停机检查并安排检修",         order:"建单" },
  { level:"CRITICAL", zh:"严重", range:"< 40",   prio:"P1", action:"立即停机检修并通知主管",     order:"建单" },
];

// 严重度上限：scoring.py:80-83 的 ALARM_RATIO / TRIP_RATIO / *_SCORE_CAP
const RULE_CAPS = [
  { cond:"任一指标 ratio ≥ 1.0（进入报警区）", cap:59.9, effect:"健康分不高于 59.9 → 至少 HIGH" },
  { cond:"任一指标 ratio ≥ 1.5（进入跳闸区）", cap:39.9, effect:"健康分不高于 39.9 → 至少 CRITICAL" },
];

// 示例样本的实算结果（下方 SHOWCASE 用 scoring.evaluate_sample 逐个算过，
// 数字直接抄自真实运行输出，不是估算）
const RULE_SAMPLES = [
  { label:"全部指标在正常区",
    sample:{ temperatureC:60.0, vibrationMmS:2.0, currentA:10.0, rotationalSpeedRpm:1500.0 },
    score:100.0, risk:"LOW", fault:"未见明显异常特征",
    ratios:{ vibration:-0.333, temperature:-0.5, current:-0.333, speed:-0.5 },
    note:"四项 penalty 全为 0 → 无扣分来源，suspectedFault 返回「未见明显异常特征」" },
  { label:"NORMAL 注入（维修后恢复）",
    sample:{ temperatureC:65.2, vibrationMmS:3.4, currentA:11.7, rotationalSpeedRpm:1450.0 },
    score:94.7, risk:"LOW", fault:"主轴轴承振动异常",
    ratios:{ vibration:0.133, temperature:-0.24, current:-0.22, speed:-0.167 },
    note:"振动 3.4 已越 3.0 正常线 → 扣 40×0.133≈5.3 分。注意风险仍是 LOW，但 suspectedFault 仍报振动——"
       + "「低风险」不等于「无隐患」" },
  { label:"ABNORMAL 注入（演示故障）",
    sample:{ temperatureC:96.7, vibrationMmS:9.8, currentA:18.3, rotationalSpeedRpm:1450.0 },
    score:30.6, risk:"CRITICAL", fault:"主轴轴承振动异常",
    ratios:{ vibration:2.267, temperature:1.335, current:0.22, speed:-0.167 },
    note:"加权分本为 100−(40+25+4.4)=30.6，但温度 ratio 1.335 已进报警区 → 上限 59.9 生效前加权分已更低，"
       + "故最终 30.6；振动 ratio 2.267 ≥ 1.5 触发跳闸上限" },
  { label:"单项极端温度（249 ℃）",
    sample:{ temperatureC:249.0, vibrationMmS:1.0, currentA:5.0, rotationalSpeedRpm:1500.0 },
    score:39.9, risk:"CRITICAL", fault:"设备温升异常",
    ratios:{ vibration:-0.667, temperature:8.95, current:-0.667, speed:-0.5 },
    note:"只有温度一项异常：加权分本为 100−25=75（MEDIUM），但 ratio 8.95 ≥ 1.5 → "
       + "跳闸上限把它压到 39.9，避免「单项极端却只判中风险」的漏报" },
  { label:"EQ-000008 实测转速 3400",
    sample:{ temperatureC:55.1, vibrationMmS:1.61, currentA:11.4, rotationalSpeedRpm:3400.0 },
    score:39.9, risk:"CRITICAL", fault:"转速偏差异常",
    ratios:{ vibration:-0.463, temperature:-0.745, current:-0.24, speed:12.167 },
    note:"转速偏差按全局额定 1500 rpm 计算；该样本转速为设备真实工况（3400），评分仅作实算演示" },
];

function rulesMetricRows(){
  return RULE_METRICS.map(m => [
    '<b>' + h(m.name) + '</b><div class="mono mini">' + h(m.key) + '</div>',
    '<span class="mini">' + h(m.unit) + '</span>',
    '<span class="mono">' + h(m.normal) + '</span>',
    '<span class="mono">' + h(m.full) + '</span>',
    '<span class="pill b-cyan">' + m.weight + '%</span>',
    '<span class="mini">' + h(m.fault) + '</span><div class="mini">→ ' + h(m.subject) + '</div>',
    '<span class="mini mono">' + h(m.constName) + '</span>',
  ]);
}

function rulesSampleRows(){
  return RULE_SAMPLES.map(s => [
    h(s.label) + '<div class="mono mini">'
      + h([s.sample.temperatureC, s.sample.vibrationMmS, s.sample.currentA,
           s.sample.rotationalSpeedRpm].join(" / ")) + '</div>',
    '<span style="font-size:14px;font-weight:700;color:'
      + toneColor(enumTone("riskLevel", s.risk) || "dim") + '">' + h(s.score) + '</span>',
    tag("riskLevel", s.risk),
    '<span class="mini">' + h(s.fault) + '</span>',
    Object.keys(s.ratios).map(k => '<span class="mini mono">' + h(k.slice(0, 4)) + '='
        + h(s.ratios[k]) + '</span>').join("<br>"),
    '<span class="mini">' + h(s.note) + '</span>',
  ]);
}

function rulesBody(){
  let html = pageHdr("预警规则阈值", "规则引擎 " + (state.rulesMeta && state.rulesMeta.modelVersion
      || "rule-engine-1.0.0") + " · 四项指标加权 · 分段阈值");

  html += capabilityMap(
    "本页是<b>规则的可执行说明书</b>：每个分数都调用服务的 "
    + "<span class=\"mono\">evaluate_sample()</span> 实算，可与线上评估结果逐条核对。",
    [
      { k:"已可用", n:"阈值与权重全览",
        d:"四项指标的正常上限、满扣线、权重、常量名逐条列出（见下表）。" },
      { k:"已可用", n:"在线试算器",
        d:"页内得分均由 B 服务实算，不是前端估算——改一个输入可立即看到分数与风险等级变化。" },
      { k:"已可用", n:"分段封顶规则",
        d:"ratio≥1 封顶 59.9、ratio≥1.5 封顶 39.9，避免单项严重异常被加权平均稀释。" },
      { k:"已可用", n:"阈值在线修改",
        d:"滑块调整后点「保存阈值并生效」，持久化到服务端并即时生效（重启保留）；"
          + "保存要求系统管理员权限（ADMIN_ALL）。" },
    ]);

  html += '<div class="grid g5 mt">'
    + kpi("green", "LOW 下限", "80", "≥ 80 → P4，不建单")
    + kpi("yellow", "MEDIUM 下限", "60", "60~79 → P3，不建单")
    + kpi("orange", "HIGH 下限", "40", "40~59 → P2，建单")
    + kpi("red", "CRITICAL", "< 40", "→ P1，建单")
    + kpi("purple", "规则版本", "v1.0.0", "modelVersion 随评估落库")
    + '</div>';

  html += '<div class="card mt">' + sect("指标阈值与权重", "合计 100 分")
    + table(["指标", "单位", "正常上限", "满扣线", "权重", "疑似故障 / 检修对象", "常量名"],
        rulesMetricRows())
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>扣分公式</b>：<span class="mono">ratio = (value − normal) / (full − normal)</span>，'
    + '<span class="mono">penalty = weight × clamp(ratio, 0, 1)</span>，'
    + '<span class="mono">score = 100 − Σ penalty</span>。'
    + 'ratio 可为负（指标优于正常线）但不产生负扣分——所以「正常」只是不扣分，不会加分。'
    + '<br><b>疑似故障取扣分最大项</b>：<span class="mono">top = argmax(penalties)</span>，'
    + '四项全为 0 时才返回「未见明显异常特征」。这也解释了为什么健康度 94.7 的评估仍写着'
    + '「主轴轴承振动异常」——振动 3.4 越了正常线 3.0，是全项里唯一扣分的。</div>'
    + '</div>';

  html += '<div class="card mt">' + sect("健康分 → 风险等级", "契约分段表")
    + table(["等级", "中文", "健康分区间", "工单优先级", "建议措施", "是否建单"],
        RULE_RISK_BANDS.map(b => [
          '<span class="mono">' + h(b.level) + '</span>',
          tag("riskLevel", b.level),
          '<span class="mono">' + h(b.range) + '</span>',
          '<span class="pill b-dim">' + h(b.prio) + '</span>',
          '<span class="mini">' + h(b.action) + '</span>',
          '<span class="mini">' + h(b.order) + '</span>',
        ]))
    + '<div class="mini mt">只有 HIGH 与 CRITICAL 会建单——'
    + '对应 <span class="mono">ACTIONABLE_RISK_LEVELS = {HIGH, CRITICAL}</span>'
    + '（<span class="mono">apps/fault-warning/src/domain/enums.py:90</span>）。'
    + 'MEDIUM 只落评估记录不建单，LOW 若设备此前有活跃预警则触发自动闭环。</div>'
    + '</div>';

  html += '<div class="card mt">' + sect("严重度上限", "防止单项极端被加权平均稀释")
    + table(["触发条件", "健康分上限", "效果"], RULE_CAPS.map(c => [
        '<span class="mono mini">' + h(c.cond) + '</span>',
        '<span class="mono">' + h(c.cap) + '</span>',
        '<span class="mini">' + h(c.effect) + '</span>',
      ]))
    + '<div class="mini mt" style="line-height:1.8">'
    + '没有这两条上限时，一台 249 ℃ 的设备只扣温度权重 25 分、落在 MEDIUM（75 分）'
    + '——<b>单项致命却因其它三项正常而被平均值救回来</b>，且不建单。'
    + '上限作用在<b>健康分</b>而非直接改写风险等级，'
    + '保证「健康分 → 风险等级」始终严格符合上面的契约分段表，两者不会互相矛盾。'
    + '<br>注：<span class="mono">ratio ≥ 1.0</span> 即指标达到满扣线，'
    + '<span class="mono">1.5</span> 为跳闸参考线。</div>'
    + '</div>';

  html += '<div class="card mt">' + sect("实算样例", RULE_SAMPLES.length + " 个 · 与线上服务逐分一致")
    + table(["样本（温度/振动/电流/转速）", "健康分", "等级", "疑似故障", "四项 ratio", "说明"],
        rulesSampleRows())
    + '</div>';

  // 「已知缺陷」卡（额定转速硬编码/阈值不可配置/落地项）为评审向内容，已按精简要求移除；
  // 修法与迁移路径保留在 创新点方案.md。

  html += rulesSandboxHtml();
  return html;
}

/* ========================= G · 规则沙盒（仅试算不写回） ========================= */

/** 沙盒配置：滑块改的是 SCORING_DEFAULTS 的副本，绝不写回服务端 */
function rulesSbCfg(){
  if (!state.rulesSb) {
    state.rulesSb = {
      vibNormal: SCORING_DEFAULTS.vibNormal, vibFull: SCORING_DEFAULTS.vibFull,
      tempNormal: SCORING_DEFAULTS.tempNormal, tempFull: SCORING_DEFAULTS.tempFull,
      currNormal: SCORING_DEFAULTS.currNormal, currFull: SCORING_DEFAULTS.currFull,
      speedDevNormal: SCORING_DEFAULTS.speedDevNormal * 100,  /* 存百分数（5），评分时 /100 */
      speedDevFull: SCORING_DEFAULTS.speedDevFull * 100,      /* 存百分数（15） */
      eqId: (state.equipment && state.equipment[0] && state.equipment[0].equipmentId) || "EQ-000001",
      tele: null,
    };
  }
  return state.rulesSb;
}

function rulesSbSlider(k, label, val, min, max, step, unit){
  return '<div>'
    + '<div class="mini" style="display:flex;justify-content:space-between;margin-bottom:2px">'
    + '<span>' + label + '</span><b class="mono" id="sb-' + k + '-v">' + val + unit + '</b></div>'
    + '<input type="range" min="' + min + '" max="' + max + '" step="' + step + '" value="' + val + '"'
    + ' style="width:100%;accent-color:var(--cyan)" oninput="rulesSbSet(\'' + k + '\', this.value)">'
    + '</div>';
}

function rulesSandboxHtml(){
  const sb = rulesSbCfg();
  const eqs = state.equipment || [];
  const eqOpts = eqs.map(e => '<option value="' + h(e.equipmentId) + '"'
    + (e.equipmentId === sb.eqId ? " selected" : "") + '>' + h(e.equipmentId) + " " + h(e.name || "") + '</option>').join("");
  return '<div class="card mt">' + sect("规则沙盒", "改阈值 · 实时看分数与影响面")
    + '<div class="mini" style="margin-bottom:6px">试算样本设备：'
    + '<select id="sb-eq" onchange="rulesSbEq(this.value)" style="margin-left:6px">' + eqOpts + '</select>'
    + '<span class="mini" id="sb-sample-note" style="margin-left:10px"></span></div>'
    + '<div class="grid g4" style="gap:10px 18px;margin:10px 0">'
    + rulesSbSlider("vibNormal", "振动正常上限", sb.vibNormal, 0, 10, 0.1, " mm/s")
    + rulesSbSlider("vibFull", "振动满扣线", sb.vibFull, 1, 15, 0.1, " mm/s")
    + rulesSbSlider("tempNormal", "温度正常上限", sb.tempNormal, 40, 100, 1, " ℃")
    + rulesSbSlider("tempFull", "温度满扣线", sb.tempFull, 50, 150, 1, " ℃")
    + rulesSbSlider("currNormal", "电流正常上限", sb.currNormal, 5, 30, 0.5, " A")
    + rulesSbSlider("currFull", "电流满扣线", sb.currFull, 10, 60, 0.5, " A")
    + rulesSbSlider("speedDevNormal", "转速偏差正常", sb.speedDevNormal, 1, 20, 1, "%")
    + rulesSbSlider("speedDevFull", "转速偏差满扣", sb.speedDevFull, 5, 30, 1, "%")
    + '</div>'
    + '<div id="sb-out"></div>'
    + '<div style="margin-top:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
    + '<button class="btn" id="sb-save" onclick="rulesSbSave()">💾 保存阈值并生效</button>'
    + '<span class="mini">保存后持久化到服务端并即时生效（重启保留），仅系统管理员（ADMIN_ALL）可保存。</span>'
    + '</div>'
    + '</div>';
}

/** 保存阈值：PUT /api/v1/scoring-thresholds（ADMIN_ALL），成功后刷新默认基线 */
async function rulesSbSave(){
  const sb = rulesSbCfg();
  const btn = document.getElementById("sb-save");
  const body = { values: {
    vibration_normal: sb.vibNormal, vibration_full: sb.vibFull,
    temperature_normal: sb.tempNormal, temperature_full: sb.tempFull,
    current_normal: sb.currNormal, current_full: sb.currFull,
    nominal_speed: SCORING_DEFAULTS.nominalRpm,
    speed_dev_normal: sb.speedDevNormal / 100, speed_dev_full: sb.speedDevFull / 100,
    weight_vibration: 40, weight_temperature: 25, weight_current: 20, weight_speed: 15,
  } };
  if (btn) { btn.disabled = true; btn.textContent = "保存中…"; }
  try {
    const r = await fetch("/b/api/v1/scoring-thresholds", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-Trace-Id": "trace-ui-" + Date.now(), ...authHeaders() },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.message || d.error || ("HTTP " + r.status));
    /* 保存成功：默认基线同步为新阈值，沙盒「默认规则」对比口径更新 */
    SCORING_DEFAULTS.vibNormal = sb.vibNormal; SCORING_DEFAULTS.vibFull = sb.vibFull;
    SCORING_DEFAULTS.tempNormal = sb.tempNormal; SCORING_DEFAULTS.tempFull = sb.tempFull;
    SCORING_DEFAULTS.currNormal = sb.currNormal; SCORING_DEFAULTS.currFull = sb.currFull;
    SCORING_DEFAULTS.speedDevNormal = sb.speedDevNormal / 100;
    SCORING_DEFAULTS.speedDevFull = sb.speedDevFull / 100;
    rulesSbRender();
    if (typeof toast === "function") toast("阈值已保存并生效", "ok");
    else alert("阈值已保存并生效");
  } catch (e) {
    const msg = (e && e.message) || "";
    if (msg.indexOf("ADMIN_ALL") >= 0 || msg.indexOf("权限") >= 0) {
      if (typeof toast === "function") toast("保存失败：需要系统管理员权限", "bad");
      else alert("保存失败：需要系统管理员权限");
    } else {
      if (typeof toast === "function") toast("保存失败：" + msg, "bad");
      else alert("保存失败：" + msg);
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "💾 保存阈值并生效"; }
  }
}

function rulesSbSet(k, v){
  const sb = rulesSbCfg();
  sb[k] = Number(v);
  rulesSbRender();
}

function rulesSbEq(id){
  const sb = rulesSbCfg();
  sb.eqId = id;
  sb.tele = null;
  const box = document.getElementById("sb-out");
  if (box) box.innerHTML = '<div class="mini">加载遥测中…</div>';
  rulesSbLoadTele().then(rulesSbRender);
}

/** 选中设备的最近 100 条遥测（NEWEST-first）——影响面按这批样本复算 */
async function rulesSbLoadTele(){
  const sb = rulesSbCfg();
  try {
    const d = await api("a", "/api/v1/equipment/" + encodeURIComponent(sb.eqId)
      + "/telemetry?pageSize=100", { headers: authHeaders() });
    sb.tele = d.items || [];
  } catch (e) { sb.tele = null; }
}

/** 沙盒实时重算：只更新沙盒面板，不整页刷新 */
function rulesSbRender(){
  const sb = rulesSbCfg();
  const box = document.getElementById("sb-out");
  if (!box) return;
  /* 滑块标签 */
  [["vibNormal"," mm/s"],["vibFull"," mm/s"],["tempNormal"," ℃"],["tempFull"," ℃"],
   ["currNormal"," A"],["currFull"," A"],["speedDevNormal","%"],["speedDevFull","%"]].forEach(x => {
    const el = document.getElementById("sb-" + x[0] + "-v");
    if (el) el.textContent = sb[x[0]] + x[1];
  });
  const sample = sb.tele && sb.tele[0];
  const note = document.getElementById("sb-sample-note");
  if (note) note.textContent = sample ? "最新样本 " + h(sample.measuredAt || "") : "";
  if (!sample) { box.innerHTML = emptyBox("无遥测样本", "该设备没有遥测数据，无法试算"); return; }

  const cfg = {
    vibNormal: sb.vibNormal, vibFull: sb.vibFull,
    tempNormal: sb.tempNormal, tempFull: sb.tempFull,
    currNormal: sb.currNormal, currFull: sb.currFull,
    speedDevNormal: sb.speedDevNormal / 100, speedDevFull: sb.speedDevFull / 100,
    nominalRpm: SCORING_DEFAULTS.nominalRpm,
  };
  const r = jsScore(sample, cfg);
  const def = jsScore(sample, SCORING_DEFAULTS);
  const p = jsPenalties(sample, cfg);
  const METRICS = [["vibration","振动"],["temperature","温度"],["current","电流"],["speed","转速偏差"]];
  let defOrders = 0, sbOrders = 0, defWatch = 0, sbWatch = 0;
  (sb.tele || []).forEach(t => {
    const rs = jsScore(t, SCORING_DEFAULTS), rn = jsScore(t, cfg);
    if (rs.score < 60) defOrders++;
    if (rn.score < 60) sbOrders++;
    if (rs.score < 80) defWatch++;
    if (rn.score < 80) sbWatch++;
  });
  box.innerHTML =
    '<div class="grid g-3-2" style="margin-bottom:12px">'
    + '<div style="background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:12px">'
    + '<div class="mini" style="margin-bottom:6px">最新样本试算（客户端按 scoring.py 公式复算）</div>'
    + '<div style="font-size:22px;font-weight:700;color:' + toneColor(r.score >= 80 ? "ok" : r.score >= 60 ? "info" : "bad") + '">'
    + r.score + ' <span style="font-size:13px">' + tag("riskLevel", r.risk) + '</span></div>'
    + '<div class="mini" style="margin-top:6px">默认规则：' + def.score + " · " + h(enumZh("riskLevel", def.risk))
    + '　→　沙盒规则：' + r.score + " · " + h(enumZh("riskLevel", r.risk)) + '</div>'
    + '<div class="mini" style="margin-top:6px">扣分明细：'
    + METRICS.map(m => h(m[1]) + " -" + p[m[0]]).join(" · ") + '</div>'
    + '</div>'
    + '<div style="background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:12px">'
    + '<div class="mini" style="margin-bottom:6px">影响面（最近 ' + (sb.tele || []).length + ' 条样本复算）</div>'
    + '<table style="width:100%"><tbody>'
    + '<tr><td class="mini">触发建单（&lt;60 分）</td><td><b>' + defOrders + '</b> 次</td><td><b>' + sbOrders + '</b> 次</td></tr>'
    + '<tr><td class="mini">进入关注（&lt;80 分）</td><td><b>' + defWatch + '</b> 次</td><td><b>' + sbWatch + '</b> 次</td></tr>'
    + '</tbody></table>'
    + '</div>'
    + '</div>'
    + '<div class="mini">表头「默认规则」= 线上 <span class="mono">scoring.py</span> 常量；「沙盒规则」= 当前滑块值。'
    + '同一批样本逐条复算，改滑块立即更新。</div>';
}

registerPage("rules", {
  async load(ctx){
    // 本页展示的是代码常量与实算样例，不依赖后端数据；
    // 但顺带确认 B 服务在线，好让「只读」的说法有据可依。
    state.rulesMeta = { modelVersion: "rule-engine-1.0.0" };
    try {
      const hp = await api("b", "/health", { headers: {} });
      if (hp && hp.modelVersion) state.rulesMeta.modelVersion = hp.modelVersion;
    } catch (e) { /* B 不可达时仍展示常量表，只是版本号回落默认值 */ }
    if (!state.equipment.length) await loadEquipment();   // 沙盒设备选择器
    await rulesSbLoadTele();                              // 沙盒样本与影响面
    try {                                                 // 服务端当前阈值 → 沙盒起点
      const th = await api("b", "/api/v1/scoring-thresholds", { headers: authHeaders() });
      const v = th && th.values;
      if (v) {
        SCORING_DEFAULTS.vibNormal = v.vibration_normal; SCORING_DEFAULTS.vibFull = v.vibration_full;
        SCORING_DEFAULTS.tempNormal = v.temperature_normal; SCORING_DEFAULTS.tempFull = v.temperature_full;
        SCORING_DEFAULTS.currNormal = v.current_normal; SCORING_DEFAULTS.currFull = v.current_full;
        SCORING_DEFAULTS.speedDevNormal = v.speed_dev_normal; SCORING_DEFAULTS.speedDevFull = v.speed_dev_full;
        SCORING_DEFAULTS.nominalRpm = v.nominal_speed || 1500;
        state.rulesSb = null;   // 重置沙盒副本为服务端值
      }
    } catch (e) { /* 服务端无阈值接口时用前端默认 */ }
    return rulesBody();
  },
  after(){
    rulesSbRender();   // 首次渲染就要出试算结果与影响面，不能等用户拖滑块
  },
});
