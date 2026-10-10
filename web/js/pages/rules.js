/* ============================================================================
 * 页面：预警规则阈值（#/rules）
 *
 * 本页展示 B 服务规则引擎的**真实常量与真实计算结果**，全部取自：
 *   apps/fault-warning/src/domain/scoring.py
 *   阈值 → 常量名与当前值一一对应（VIBRATION_NORMAL_MM_S 等）
 *   示例得分 → 用该服务的 evaluate_sample() 实算，非手写
 *
 * 边界说明（必须写清，否则就是骗人）：
 *   阈值与权重目前是**代码常量**，只能改代码 + 重启服务来调整；契约没有
 *   "配置阈值"的写接口，所以本页**没有「保存生效」按钮**——不做假开关。
 *   要变成可配置，需新增 warning_rule 表 + 读写接口（见页内落地清单）。
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
    note:"⚠ 这一行暴露了当前引擎的真实缺陷：NOMINAL_SPEED_RPM 是全局常量 1500，"
       + "而八号激光切割机额定转速并非 1500 → 一旦该设备被评估就会误判 CRITICAL。"
       + "详见页内「已知缺陷」" },
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

  html += noticePlan("当前阈值与权重是<b>代码常量</b>，定义在 "
    + "<span class=\"mono\">apps/fault-warning/src/domain/scoring.py</span>"
    + "（<span class=\"mono\">WEIGHTS</span> 与四个 <span class=\"mono\">*_NORMAL/FULL_*</span> 常量）。"
    + "契约里没有「配置阈值」的写接口，因此本页<b>只读</b>——"
    + "不做「保存并生效」的假按钮。页内所有得分都是调用该服务的 "
    + "<span class=\"mono\">evaluate_sample()</span> 实算出来的，不是估算值。");

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

  html += '<div class="card mt">' + sect("实算样例", RULE_SAMPLES.length + " 个（调用 scoring.evaluate_sample 得出）")
    + table(["样本（温度/振动/电流/转速）", "健康分", "等级", "疑似故障", "四项 ratio", "说明"],
        rulesSampleRows())
    + '</div>';

  html += '<div class="card mt">' + sect("已知缺陷", "必须写明，否则就是骗人")
    + '<div class="timeline">'
    + '<div class="tl warn"><div class="tt">额定转速被硬编码为 1500 rpm，跨设备误判</div><div class="td">'
      + '<span class="mono">scoring.py:71</span> 的 '
      + '<span class="mono">NOMINAL_SPEED_RPM = 1500.0</span> 是<b>全局常量</b>，'
      + '而额定转速本是设备属性：五号离心泵 2900 rpm、七号传送带 420 rpm、'
      + '八号激光切割机 3400 rpm 都是各自正常工况。'
      + '一旦这些设备被评估，转速 ratio 会算出 6.7 / 12.2 这类数值 → '
      + '<b>一律误判 CRITICAL 并建 P1 工单</b>。'
      + '上面第 5 个样例就是这个误判的实算复现。'
      + '<br>根因：<span class="mono">apps/equipment-monitoring/src/domain/models.py</span> 的 '
      + 'Equipment 没有额定转速字段，B 无从得知每台设备的额定值。'
      + '<br>修法（未决策）：① 给 Equipment 加 <span class="mono">ratedSpeed</span> 并让 scoring 读设备额定值'
      + '（需迁移 + <span class="mono">scripts/reset_demo.py</span> 覆盖重建路径）；'
      + '② 把演示种子转速改成各自额定值附近。'
      + '②更省事但只是掩盖，①才是正解。</div></div>'
    + '<div class="tl ok"><div class="tt">阈值不可配置</div><div class="td">'
      + '四项阈值与权重写死在代码里，改一次要改代码 + 重启 B 服务。'
      + '不同设备类型（机床 / 泵 / 风机 / 空压机）的正常区间差异很大，'
      + '硬编码意味着每接一类新设备都要改代码发版。</div></div>'
    + '</div>'
    + table(["落地项", "需要什么", "优先级"], [
        ["阈值可配置化", "新增 <span class=\"mono mini\">warning_rule</span> 表 + "
          + "<span class=\"mono mini\">GET/PUT /api/v1/warning-rules</span>；"
          + "按设备类型覆盖 + 变更留审计", '<span class="pill b-red">P1</span>'],
        ["设备额定转速", "Equipment 加 <span class=\"mono mini\">ratedSpeed</span> 字段；"
          + "scoring 改为读设备额定值而非全局常量", '<span class="pill b-red">P1</span>'],
        ["连续 N 次异常才建单", "评估侧记连续计数，防抖；当前单次即建单", '<span class="pill b-yellow">P2</span>'],
        ["模型置信度低时转人工", "需影子模型双轨跑分（见模型管理页）", '<span class="pill b-purple">P3</span>'],
      ])
    + '</div>';

  return html;
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
    return rulesBody();
  },
});
