/* ============================================================================
 * 页面：设备档案与铭牌（#/profile）
 *
 * 数据来源（真实）：
 *   A GET /api/v1/equipment?pageSize=100    设备主数据
 *   C GET /api/v1/work-orders               维修历史（按设备聚合）
 *   B GET /api/v1/warnings                  预警历史（按设备聚合）
 *
 * ★ 边界说明（本页最要紧的一条）：
 *   Equipment 模型**只有 11 个字段**（equipmentId / name / equipmentType /
 *   productionLineId / location / manufacturer / model / responsibleDepartment /
 *   currentStatus / enabled / version），没有出厂编号、投运日期、资产原值、
 *   保修截止、额定功率、保养周期、附件这些**静态档案字段**。
 *   所以本页：
 *     ① 铭牌只印真实存在的字段；
 *     ② 档案完备度按「契约字段里填了哪些」实算，不是编造的百分比；
 *     ③ 缺失字段列成待建清单，标明需要扩模型 + 迁移；
 *     ④ 维修/预警历史来自真实工单与预警表，可核对。
 *   原型里那些 ¥486000、保修到期日之类数字是**示意**，本页一律不编。
 * ==========================================================================*/

// Equipment 契约里全部字段 → 中文名 + 是否属于"静态档案"（区别于运行态）
const PROFILE_FIELDS = [
  { key:"equipmentId",           zh:"设备编号", archive:true,  structural:true },
  { key:"name",                  zh:"设备名称", archive:true,  structural:true },
  { key:"equipmentType",         zh:"设备类型", archive:true,  structural:true },
  { key:"productionLineId",      zh:"所属产线", archive:true,  structural:true },
  { key:"location",              zh:"安装位置", archive:true,  structural:true },
  { key:"manufacturer",          zh:"制造厂商", archive:true },
  { key:"model",                 zh:"规格型号", archive:true },
  { key:"responsibleDepartment", zh:"责任部门", archive:true },
  { key:"currentStatus",         zh:"当前状态", archive:false },
  { key:"enabled",               zh:"启用标志", archive:false },
  { key:"version",               zh:"版本号",   archive:false },
];

// 需要扩模型才能有的静态档案字段（原型画了但模型里没有）
const PROFILE_MISSING_FIELDS = [
  { zh:"出厂编号",   en:"serialNumber",     use:"保修索赔凭据、批次质量追溯", prio:"P1" },
  { zh:"投运日期",   en:"commissionedAt",   use:"役龄、折旧计算、寿命预测的基准", prio:"P1" },
  { zh:"额定转速",   en:"ratedSpeed",       use:"修正规则引擎的转速偏离判定（见预警规则页）", prio:"P1" },
  { zh:"资产原值",   en:"assetValue",       use:"停机损失核算（原值 × 停机时长）", prio:"P2" },
  { zh:"保修截止",   en:"warrantyUntil",    use:"到期提醒，避免过保后才报修", prio:"P2" },
  { zh:"额定功率",   en:"ratedPower",       use:"工况阈值自适应", prio:"P2" },
  { zh:"保养周期",   en:"maintenanceCycle", use:"预防性维护排程", prio:"P3" },
  { zh:"随机附件",   en:"attachments",      use:"说明书、图纸、验收单", prio:"P3" },
];

// 设备类型中文（A 的 seed.py 用这些码；契约里 equipmentType 是自由字符串，
// 故此处是**展示用映射**，遇到未收录的码原样显示而不是猜）
const EQ_TYPE_ZH = {
  CNC:"数控机床", MACHINING_CENTER:"加工中心", COLD_HEADER:"冷镦机",
  AIR_COMPRESSOR:"空压机", CENTRIFUGAL_PUMP:"离心泵", FAN:"风机",
  CONVEYOR:"传送带", LASER_CUTTER:"激光切割机",
};

function eqTypeZh(code){
  return EQ_TYPE_ZH[code] || code || "—";
}

/** 某设备的档案完备度：按契约字段里实际有值的比例实算 */
function profileCompleteness(eq){
  const archive = PROFILE_FIELDS.filter(f => f.archive);
  const filled = archive.filter(f => eq[f.key] != null && eq[f.key] !== "");
  return {
    filled: filled.length,
    total: archive.length,
    pct: Math.round(filled.length / archive.length * 100),
    missing: archive.filter(f => !(eq[f.key] != null && eq[f.key] !== "")),
  };
}

/** 某设备的维修与预警历史（来自真实工单与预警表） */
function profileHistoryOf(eqId){
  const orders = (state.orders || []).filter(o => o.equipmentId === eqId);
  const warns  = (state.warnings || []).filter(w => w.equipmentId === eqId);
  const done = orders.filter(o => o.status === "COMPLETED");
  const downtime = done.reduce((s, o) => s + (o.downtimeMinutes || 0), 0);
  const effDone = done.filter(o => o.effective === true).length;
  return {
    orders: orders, warns: warns, completed: done,
    open: orders.filter(o => !["COMPLETED","CANCELLED"].includes(o.status)),
    downtime: downtime,
    effectiveRate: done.length ? Math.round(effDone / done.length * 100) : null,
  };
}

/** 铭牌卡片：只印真实字段 */
function profileNameplateHtml(eq){
  const h2 = profileHistoryOf(eq.equipmentId);
  const c = profileCompleteness(eq);
  const stTone = eq.enabled === false ? "dim"
    : eq.currentStatus === "RUNNING" ? "green"
    : eq.currentStatus === "MAINTAINING" ? "red" : "yellow";
  return '<div class="plate">'
    + '<div class="plate-hdr">'
    + '<div><div class="plate-eq mono">' + h(eq.equipmentId) + '</div>'
    + '<div class="plate-nm">' + h(eq.name) + '</div></div>'
    + '<div style="text-align:right"><span class="pill b-' + stTone + '">'
      + h(eq.enabled === false ? "已停用"
            : enumZh("equipmentStatus", eq.currentStatus, eq.currentStatus))
      + '</span><div class="mini mono" style="margin-top:4px">v' + h(eq.version) + '</div></div>'
    + '</div>'
    + '<div class="plate-grid">'
    + '<div><span class="pk">设备类型</span><span class="pv">' + h(eqTypeZh(eq.equipmentType)) + '</span></div>'
    + '<div><span class="pk">规格型号</span><span class="pv mono">' + h(eq.model || "—") + '</span></div>'
    + '<div><span class="pk">制造厂商</span><span class="pv">' + h(eq.manufacturer || "—") + '</span></div>'
    + '<div><span class="pk">所属产线</span><span class="pv mono">' + h(eq.productionLineId || "—") + '</span></div>'
    + '<div><span class="pk">安装位置</span><span class="pv">' + h(eq.location || "—") + '</span></div>'
    + '<div><span class="pk">责任部门</span><span class="pv">' + h(eq.responsibleDepartment || "—") + '</span></div>'
    + '</div>'
    + '<div class="plate-foot">'
    + '<span class="mini">档案完备度 <b style="color:'
      + (c.pct >= 90 ? "var(--green)" : c.pct >= 60 ? "var(--yellow)" : "var(--red)") + '">'
      + c.pct + '%</b>（' + c.filled + '/' + c.total + ' 项）</span>'
    + '<span class="mini">历史工单 ' + h2.orders.length + ' · 预警 ' + h2.warns.length
      + (h2.effectiveRate != null ? ' · 有效率 ' + h2.effectiveRate + '%' : '') + '</span>'
    + '</div></div>';
}

function profileTableRows(){
  return (state.equipment || []).map(eq => {
    const c = profileCompleteness(eq);
    const h2 = profileHistoryOf(eq.equipmentId);
    const tone = c.pct >= 90 ? "ok" : c.pct >= 60 ? "warn" : "bad";
    return [
      '<span class="mono">' + h(eq.equipmentId) + '</span>'
        + '<div class="mini">' + h(eq.name) + '</div>',
      '<span class="mini">' + h(eqTypeZh(eq.equipmentType)) + '</span>',
      '<span class="mono mini">' + h(eq.model || "—") + '</span>',
      '<span class="mini">' + h(eq.manufacturer || "—") + '</span>',
      '<span class="mono mini">' + h(eq.productionLineId || "—") + '</span>',
      '<span class="mini">' + h(eq.responsibleDepartment || "—") + '</span>',
      '<div style="display:flex;align-items:center;gap:6px">'
        + '<span style="display:inline-block;width:58px;height:5px;border-radius:3px;'
        + 'background:var(--line);overflow:hidden"><span style="display:block;height:100%;'
        + 'width:' + c.pct + '%;background:' + toneColor(tone) + '"></span></span>'
        + '<span class="mini mono">' + c.pct + '%</span></div>',
      '<span class="mini">' + h2.orders.length + '</span>',
      '<span class="mini">' + h2.warns.length + '</span>',
      '<span class="mini mono">' + (h2.downtime ? h2.downtime + " min" : "—") + '</span>',
      '<button class="btn btn-o btn-sm" onclick="navigate(\'detail\',{equipmentId:\''
        + h(eq.equipmentId) + '\'})">详情</button>',
    ];
  });
}

function profileBody(){
  const eqs = state.equipment || [];
  const avg = eqs.length
    ? Math.round(eqs.reduce((s, e) => s + profileCompleteness(e).pct, 0) / eqs.length) : 0;
  const full = eqs.filter(e => profileCompleteness(e).pct === 100).length;
  const elems = eqs.filter(e => !e.model || !e.manufacturer || !e.responsibleDepartment).length;

  let html = pageHdr("设备档案与铭牌",
    "资产主数据 · " + eqs.length + " 台设备 · 字段与台账页同源");

  html += noticePlan("Equipment 模型目前只有 <b>11 个字段</b>——"
    + "<span class=\"mono\">equipmentId / name / equipmentType / productionLineId / location / "
    + "manufacturer / model / responsibleDepartment / currentStatus / enabled / version</span>。"
    + "其中后三个是<b>运行态</b>，真正的「档案」只有 8 个。"
    + "出厂编号、投运日期、资产原值、保修截止、<b>额定转速</b>、附件等静态字段<b>模型里没有</b>，"
    + "所以本页不印它们、也不编数字——只把「已有哪些、缺哪些、缺了影响什么」列清楚。"
    + "铭牌卡片里的每个值都能在设备台账页找到同源出处。");

  html += '<div class="grid g4 mt">'
    + kpi("cyan", "在册设备", eqs.length, "来自 A 设备主数据")
    + kpi(avg >= 90 ? "green" : "yellow", "平均档案完备度", avg + "%", "按契约 8 个档案字段实算")
    + kpi(full === eqs.length ? "green" : "yellow", "字段齐全", full + " / " + eqs.length,
        "8 项档案字段全部有值")
    + kpi(elems ? "yellow" : "green", "关键字段缺失", elems + " 台",
        elems ? "缺型号 / 厂商 / 责任部门" : "型号与厂商均已登记")
    + '</div>';

  html += '<div class="card mt">' + sect("铭牌卡片", "可直接与车间实物铭牌核对")
    + '<div class="plate-grid-wrap">' + eqs.map(profileNameplateHtml).join("") + '</div>'
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>关于「二维码铭牌」</b>：原型画了二维码，但当前环境没有可用的二维码库'
    + '（无 <span class="mono">qrcode</span> 依赖、无外网 CDN），'
    + '所以本页不画一个扫不出东西的假二维码。'
    + '现场真要扫码时，二维码内容只需是设备详情页链接'
    + '（<span class="mono">#/detail?equipmentId=EQ-000001</span>）——'
    + '现在直接把这个编号输入顶栏搜索框，效果与扫码一致，且不需要任何后端改动。'
    + '</div></div>';

  html += '<div class="card mt">' + sect("档案完备度总表", "按设备")
    + table(["设备", "类型", "型号", "厂商", "产线", "责任部门", "完备度",
             "工单", "预警", "累计停机", "操作"], profileTableRows())
    + '<div class="mini mt">「工单 / 预警 / 累计停机」都由本页从真实表聚合：'
    + '工单来自 C <span class="mono">work_order</span>、预警来自 B '
    + '<span class="mono">warning</span>、停机时长取已完成工单的 '
    + '<span class="mono">downtime_minutes</span> 之和（未结工单不计，计了会偏低）。'
    + '可在工单列表页与预警中心页交叉验证。</div>'
    + '</div>';

  html += '<div class="card mt">' + sect("契约字段清单",
      PROFILE_FIELDS.length + " 项（8 档案 + 3 运行态）")
    + table(["字段", "中文", "类别", "来源", "本页用途"], PROFILE_FIELDS.map(f => [
        '<span class="mono">' + h(f.key) + '</span>',
        h(f.zh),
        f.archive ? '<span class="pill b-cyan">档案</span>'
                  : '<span class="pill b-dim">运行态</span>',
        '<span class="mini">A 主数据' + (f.structural ? '（建档时确定）' : '（受事件驱动变更）') + '</span>',
        '<span class="mini">' + (f.archive ? "铭牌印刷 + 完备度分母" : "铭牌状态角标") + '</span>',
      ]))
    + '</div>';

  html += '<div class="card mt">' + sect("待扩字段清单", "需改模型，故单列")
    + table(["字段", "英文名", "缺了会影响什么", "优先级"], PROFILE_MISSING_FIELDS.map(f => [
        '<b>' + h(f.zh) + '</b>',
        '<span class="mono mini">' + h(f.en) + '</span>',
        '<span class="mini">' + h(f.use) + '</span>',
        '<span class="pill b-' + (f.prio === "P1" ? "red" : f.prio === "P2" ? "yellow" : "dim")
          + '">' + h(f.prio) + '</span>',
      ]))
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>落地路径（按 AGENTS.md 要求给迁移方案）</b>：新增 '
    + '<span class="mono">equipment_profile</span> 表（1:1 关联 equipment，'
    + '避免把静态档案混进高频更新的主表），提供 '
    + '<span class="mono">GET/PUT /api/v1/equipment/{equipmentId}/profile</span>，'
    + '并在 <span class="mono">scripts/reset_demo.py</span> 里覆盖重建路径。'
    + '<br>其中 <span class="mono">ratedSpeed</span> 优先级最高——它不只影响档案页，'
    + '还是预警规则页那个「额定转速硬编码 1500 导致跨设备误判」缺陷的正解。'
    + '</div></div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("为什么档案值得单做一页", "运维决策依赖它")
    + '<div class="timeline">'
    + '<div class="tl warn"><div class="tt">保修是否还在期内</div><div class="td">'
      + '过保设备报修要走内部预算，保修期内应走厂商渠道。'
      + '判断依据只有投运日期与保修截止——<b>这两个字段现在都没有</b>。</div></div>'
    + '<div class="tl ok"><div class="tt">同型号横向对比</div><div class="td">'
      + '两台同型号设备一台老出问题一台没事，先要确认规格型号一致。'
      + '<span class="mono">model</span> 字段已有，这一步已能支撑。</div></div>'
    + '<div class="tl warn"><div class="tt">该不该换新</div><div class="td">'
      + '役龄 + 维修累计成本 vs 资产原值，是换新决策的标准算法。'
      + '现在只能拿到维修次数（本页已算），拿不到役龄与原值。</div></div>'
    + '<div class="tl ok"><div class="tt">知识沉淀的入口</div><div class="td">'
      + '档案 + 维修历史 = 设备全生命周期台账，是后续 RAG 与寿命预测的语料来源。'
      + '本页的工单 / 预警 / 停机统计就是这个方向的起点，且全部来自真实表。</div></div>'
    + '</div></div>'

    + '<div class="card">' + sect("统计口径", "可交叉验证")
    + table(["统计项", "口径"], [
        ["历史工单", 'C <span class="mono mini">work_order</span> 中 '
          + '<span class="mono mini">equipment_id</span> 匹配的全部记录（含已取消）'],
        ["预警条数", 'B <span class="mono mini">warning</span> 中同设备的全部记录'],
        ["累计停机", '已完成工单的 <span class="mono mini">downtime_minutes</span> 求和；'
          + '未结工单不计'],
        ["维修有效率", '已完成工单中 <span class="mono mini">effective=true</span> 的比例；'
          + '无已完成工单时显示「—」而不是 0%'],
      ].map(r => [h(r[0]), '<span class="mini">' + r[1] + '</span>']))
    + '<div class="mini mt">本页不做独立数据副本，只做聚合视图——'
      + '同一份数据在工单列表页与预警中心页看到的数字应当一致。</div>'
    + '</div></div>';

  return html;
}

registerPage("profile", {
  async load(ctx){
    await Promise.all([
      loadEquipment(), loadOrders(), loadWarnings(),
    ].map(p => Promise.resolve(p).catch(() => null)));
    return profileBody();
  },
});
