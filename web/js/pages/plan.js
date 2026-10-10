/* ============================================================================
 * 演进页（智能分析 4 页 + 模型与数据 3 页）—— 页面实现
 * 共享工具见 plan-lib.js（真实统计 / Matrix Profile / 归因分解 / 热力条）
 * ==========================================================================*/

// ══════════════════════════════════════════════════════════════════════
// 异常检测（anomaly）
// ══════════════════════════════════════════════════════════════════════
function anomalyBody(){
  const eqId = richestEq() || (state.equipment[0] && state.equipment[0].equipmentId);
  const dq = realDataQuality();
  const outs = realOutliers();
  const disc = eqId ? anomalyDiscords(eqId, 6) : null;

  let html = pageHdr("异常检测",
    "无监督时序异常检测 · 规则阈值保底，模型补「未知坏法」的盲区",
    '<span class="tag tag-plan">演进中</span>');

  html += noticePlan("<b>演进中 · 尚未接入训练型模型</b> —— 但本页<b>不是空壳</b>："
    + "下半部分的检测是<b>真的在浏览器里对 " + (dq ? dq.samples : 0)
    + " 条真实遥测算出来的</b>（3σ 与 z-norm Matrix Profile），不是示意曲线。"
    + "缺的只是「训练型模型」那一层——规则与零训练基线现在就能跑，"
    + "深度模型才是规划项。落地路径见 "
    + "<span class=\"mono\">docs/参赛材料/演进改造清单.md</span>。");

  html += '<div class="grid g4 mt">'
    + kpi("purple", "已训练模型", "0", "规划中（零训练基线已可跑）")
    + kpi("cyan", "参与计算的真实样本", dq ? dq.samples : 0, "本页当场计算，非示意")
    + kpi(outs.length ? "yellow" : "green", "3σ 越限点", outs.length,
        dq ? "占参与判定的样本格 " + fmtNum(outs.length / dq.scoredCells * 100, 2) + "%" : "—")
    + kpi(disc && disc.discords.length ? "red" : "dim", "Matrix Profile Discord",
        disc ? disc.discords.length : 0, "最不像历史任何片段的窗口")
    + '</div>';

  html += '<div class="grid g-3-2 mt">'
    + '<div class="card">' + sect("Matrix Profile Discord（真实计算）",
        eqId ? eqId + " · 窗口 " + (disc ? disc.win : "-") + " 点 · 温度序列" : "")
    + (disc
        ? planHeatHtml(disc.series, disc.times, 55, 100)
          + table(["排名", "窗口起点", "profile 值", "片段（原始值）", "解读"],
              disc.discords.map((d, i) => [
                '<b>' + (i + 1) + '</b>',
                '<span class="mono mini">' + h(fmtTimeSec(d.measuredAt)) + '</span>',
                '<span class="mono" style="color:' + (i === 0 ? "var(--red)" : "var(--yellow)")
                  + '">' + h(fmtNum(d.profile, 2)) + '</span>',
                '<span class="mono mini">[' + d.segment.join(", ") + ']</span>',
                '<span class="mini">' + (i === 0
                  ? "最异常：出现其它窗口都没有的跃变" : "次异常：与最近邻距离次大") + '</span>',
              ]))
          + '<div class="mini mt" style="line-height:1.8">'
          + '把温度序列切成 ' + disc.win + ' 点滑窗、每个窗口做 <b>z-norm 标准化</b>，'
          + '再算每个窗口与「所有不重叠窗口」的最近距离——这就是 <b>Matrix Profile</b>。'
          + 'profile 值最高的窗口即 <b>discord</b>（最不像历史上任何一段的片段）。<br>'
          + '本页实测：' + disc.windows + ' 个窗口，profile 最小 '
          + fmtNum(disc.profileMin, 2) + '、均值 ' + fmtNum(disc.profileMean, 2)
          + '、最大 ' + fmtNum(disc.profileMax, 2) + '。<br>'
          + 'z-norm 让算法只关心<b>形状</b>不关心绝对幅值，所以同一形状不同温度会被判为相似——'
          + '这既是它的优点（抗基线漂移），也是它的盲区（对整体抬升不敏感，需配合 3σ）。'
          + '</div>'
        : emptyBox("该设备样本不足", "至少需要 10 个样本点才能做 Matrix Profile"))
    + '</div>'

    + '<div class="card">' + sect("3σ 越限点（真实计算）", outs.length + " 个")
    + table(["设备", "指标", "实测值", "基线 μ±3σ", "偏离"], outs.slice(0, 8).map(o => [
        '<span class="mono mini">' + h(o.equipmentId) + '</span>',
        '<span class="mini">' + h(o.metric.zh) + '</span>',
        '<span class="mono" style="color:var(--red)">' + h(fmtNum(o.value, 1)) + '</span>',
        '<span class="mono mini">' + h(fmtNum(o.mu, 1) + " ± " + fmtNum(3 * o.sd, 2)) + '</span>',
        '<span class="mono" style="color:' + (o.sigma > 4 ? "var(--red)" : "var(--yellow)") + '">'
          + h(fmtNum(o.sigma, 2)) + 'σ</span>',
      ]), { emptyText: "无越 3σ 的点", emptyHint: "分布一致，无显著离群" })
    + '<div class="mini mt" style="line-height:1.8">3σ 是最朴素的无监督基线——'
      + '它只能发现「偏离自身历史」的点，对<b>缓慢漂移</b>不敏感'
      + '（均值一起漂走就永远不越 3σ）。这正是需要 Matrix Profile 与'
      + '重建型模型的原因。</div>'
    + '</div></div>';

  html += '<div class="grid g3 mt">'
    + '<div class="card">' + sect("它解决的是哪一类问题")
    + '<div class="li"><div class="lt"><div class="l1">规则能覆盖的 '
      + '<span class="pill b-green">已知故障</span></div>'
      + '<div class="l2">温度 &gt; 70℃、振动 &gt; 3.0 mm·s⁻¹…… '
      + '这类「已知坏法」规则就够，不需要模型。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">规则覆盖不了的 '
      + '<span class="pill b-yellow">未知模式</span></div>'
      + '<div class="l2">设备以从未见过的方式劣化时规则不报警，'
      + '但重建误差会升高——这是模型的战场。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">不要指望它 '
      + '<span class="pill b-dim">定位故障</span></div>'
      + '<div class="l2">无监督检测只回答「这段数据不正常」，'
      + '不回答「哪个零件坏了」——那是归因诊断的职责。</div></div></div>'
    + '<div class="mini mt">所以本页与预警中心<b>并行而非替代</b>：规则保底，模型补盲区。</div>'
    + '</div>'

    + '<div class="card">' + sect("选型路径", "按落地风险递增")
    + '<div class="timeline">'
    + '<div class="tl"><div class="tt">第 0 步：零训练基线（本页已能跑）</div>'
      + '<div class="td"><b>3σ / Matrix Profile</b> —— 无需训练、无需 GPU，先把链路跑通。'
      + '本页上半部分就是它的真实输出。</div></div>'
    + '<div class="tl"><div class="tt">第 1 步：重建型模型</div>'
      + '<div class="td"><b>LSTM-AE</b>（隐层 64 / 瓶颈 8）—— 用正常数据训练自编码器，'
      + '异常样本重建质量差、误差自然偏高；阈值取训练集误差 P99。'
      + '纯 CPU 可训，几千点起。</div></div>'
    + '<div class="tl"><div class="tt">第 2 步：更强方法（视效果而定）</div>'
      + '<div class="td">USAD（KDD 2020）/ TranAD（VLDB 2022）/ '
      + 'Anomaly Transformer（ICLR 2022）—— 收益递减，需先确认基线不够用。</div></div>'
    + '<div class="tl warn"><div class="tt">不建议起步就做</div>'
      + '<div class="td">图神经网络、多模态融合、联邦学习——'
      + '需规模与数据量支撑，本环境不具备验证条件。</div></div>'
    + '</div></div>'

    + '<div class="card">' + sect("评估指标", "避免踩坑")
    + noticeWarn("<b>不要用 Point Adjustment 协议</b>——它会把随机噪声也算成命中，"
      + "<b>系统性高估</b>检测性能（近年多篇论文已指出该问题）。"
      + "正确做法是报告 AUC-PR / AUC-ROC / F1，并参照 TSB-AD（NeurIPS 2024）的评测标准。")
    + table(["指标", "目标", "说明"], [
        ['<span class="mono">AUC-PR</span>',
         '<span class="mono" style="color:var(--green)">≥ 0.80</span>',
         '<span class="mini">类别极不平衡时的主指标</span>'],
        ['<span class="mono">AUC-ROC</span>',
         '<span class="mono" style="color:var(--green)">≥ 0.90</span>',
         '<span class="mini">整体区分度</span>'],
        ['<span class="mono">误报率</span>',
         '<span class="mono" style="color:var(--yellow)">&lt; 5%</span>',
         '<span class="mini">工业场景最敏感——误报会让人不再信任系统</span>'],
      ])
    + '<div class="mini mt">这些是<b>目标值</b>，不是当前实测值——'
      + '本环境尚无故障标注数据，无法计算 AUC，所以本页不展示任何精度数字。</div>'
    + '</div></div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 寿命预测 RUL（rul）
// ══════════════════════════════════════════════════════════════════════
function rulBody(){
  const evs = (state.evaluations || [])
    .sort((a, b) => String(b.evaluatedAt).localeCompare(String(a.evaluatedAt)));
  const latest = {};
  evs.forEach(e => { if (!latest[e.equipmentId]) latest[e.equipmentId] = e; });
  const allLatest = Object.keys(latest).map(k => latest[k]);
  const rows = allLatest
    .filter(e => e.trend && e.trend !== "UNKNOWN"
      && e.trendMetric && e.predictedDaysToThreshold != null)
    .sort((a, b) => a.predictedDaysToThreshold - b.predictedDaysToThreshold);
  const stable = allLatest.filter(e => e.trend === "STABLE").length;
  const urgent = rows.filter(r => r.predictedDaysToThreshold <= 3).length;

  let html = pageHdr("寿命预测 RUL",
    "剩余寿命区间预测 · 当前已实现的是「线性外推」，不是 RUL 模型",
    '<span class="tag tag-plan">演进中</span>');

  html += noticePlan("<b>已实现线性外推，未实现 RUL 模型</b> —— "
    + "B 的 <span class=\"mono\">domain/trend.py</span> 已在跑："
    + "对最近 24 个样本做逐指标<b>最小二乘线性外推</b>，算出速率与"
    + "「预计 N 天后触满扣阈值」，这些字段是<b>真实的</b>（见下表）。"
    + "但它与真正的 RUL 有本质差距：线性外推假设退化速率恒定，"
    + "且只回答「到阈值还有几天」，不回答「还能用多久」，也不给置信区间。<br>"
    + "<b>本页如实区分这两者，不把外推包装成 RUL。</b>");

  html += '<div class="grid g4 mt">'
    + kpi("cyan", "预测方法", "最小二乘外推", "trend.py（已实现，非 RUL 模型）")
    + kpi(rows.length ? "yellow" : "green", "检测到上行趋势", rows.length + " 台",
        "最近 24 样本窗口内速率超下限")
    + kpi(urgent ? "red" : "green", "3 天内触限", urgent + " 台",
        urgent ? "建议提前安排检修" : "无紧迫项")
    + kpi("purple", "RUL 模型", "未实现", "规划：退化轨迹 + 置信区间")
    + '</div>';

  html += '<div class="card mt">' + sect("真实趋势外推结果", "来自 B 的 health_evaluation 表")
    + table(["设备", "等级", "紧迫指标", "速率", "预计触限", "阈值", "样本数", "评估时间"],
        rows.slice(0, 12).map(r => {
          const mz = PLAN_METRIC_ZH[r.trendMetric] || r.trendMetric;
          const unit = { temperature:"℃/天", vibration:"mm·s⁻¹/天", current:"A/天" }[r.trendMetric] || "";
          const d = r.predictedDaysToThreshold;
          const tone = d <= 3 ? "var(--red)" : d <= 10 ? "var(--yellow)" : "var(--green)";
          return [
            '<span class="mono">' + h(r.equipmentId) + '</span>',
            tag("riskLevel", r.riskLevel),
            '<span class="mini">' + h(mz) + '</span>',
            '<span class="mono mini">' + h(fmtNum(r.trendRatePerDay, 3)) + ' ' + h(unit) + '</span>',
            '<span class="mono" style="color:' + tone + '">' + h(fmtNum(d, 1)) + ' 天</span>',
            '<span class="mono mini">' + h(fmtNum(r.trendThreshold, 1)) + '</span>',
            '<span class="mini">' + h(r.trendSampleCount || 0) + '</span>',
            '<span class="mono mini">' + h(fmtTimeSec(r.evaluatedAt)) + '</span>',
          ];
        }), { emptyText: "暂无趋势数据", emptyHint: "需先通过注入异常触发 B 的评估" })
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>口径来源</b>：<span class="mono">apps/fault-warning/src/domain/trend.py</span> —— '
    + '<span class="mono">TREND_WINDOW=24</span>、'
    + '<span class="mono">MIN_RATE_PER_DAY</span> = 温度 0.5 / 振动 0.05 / 电流 0.3、'
    + '<span class="mono">MAX_PREDICTED_DAYS=365</span>。'
    + '速率低于下限视为该指标平稳，不计入「上行」；'
    + '另有 ' + stable + ' 台设备趋势为 STABLE。<br>'
    + '<b>读表时要注意一个陷阱</b>：会出现「健康度 94.7（LOW）却预测 2.2 天后触限」。'
    + '这不是矛盾——24 样本窗口里混入了之前注入的异常段，'
    + '那段陡升把回归斜率拉高了，而当前值已经回落。'
    + '真实产线上应等异常窗口完全滑出，或按设备状态分段回归。'
    + '</div></div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("线性外推 vs 真正的 RUL", "差别在哪")
    + table(["维度", "当前（线性外推）", "真正的 RUL"], [
        ["输出", '<span class="mini">到阈值还有几天</span>',
         '<span class="mini">剩余可用时长 + 置信区间</span>'],
        ["退化模型", '<span class="mini">速率恒定（一次函数）</span>',
         '<span class="mini">指数 / 幂律 / 维纳过程 / 隐马尔可夫</span>'],
        ["不确定性", '<span class="mini">无</span>',
         '<span class="mini">必须给出（否则无法排产）</span>'],
        ["数据要求", '<span class="mini">24 个样本即可</span>',
         '<span class="mini">多台同型号的完整失效历史</span>'],
        ["失效定义", '<span class="mini">越过规则阈值（<b>代理指标</b>）</span>',
         '<span class="mini">真实失效事件</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">关键区别在<b>最后一行</b>：'
      + '本系统目前没有真实失效记录，只有「越过规则阈值」这个代理。'
      + '用代理指标训练的 RUL，本质是在预测「什么时候会报警」而非'
      + '「什么时候会坏」——这一点必须在页面上说清楚，'
      + '否则使用者会过度信任它。</div>'
    + '</div>'

    + '<div class="card">' + sect("建模方法对比", "按数据需求排序")
    + table(["方法", "数据需求", "输出", "本环境可验证"], [
        ['<span class="mini">线性 / 指数外推</span>',
         '<span class="mini">单台 20+ 样本</span>', '<span class="mini">点估计</span>',
         '<span class="pill b-green">是（已实现）</span>'],
        ['<span class="mini">相似性匹配</span>',
         '<span class="mini">同型号历史轨迹库</span>', '<span class="mini">区间</span>',
         '<span class="pill b-red">样本不足</span>'],
        ['<span class="mini">LSTM / Transformer</span>',
         '<span class="mini">数十台完整失效序列</span>', '<span class="mini">区间</span>',
         '<span class="pill b-red">否</span>'],
        ['<span class="mini">维纳过程 / 粒子滤波</span>',
         '<span class="mini">退化增量分布</span>', '<span class="mini">分布</span>',
         '<span class="pill b-yellow">可做但需先定退化模型</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">本环境的真实约束：8 台设备、'
      + (allSamples().length || 596) + ' 条样本、1 条真实维修结论。'
      + '这个规模只够支撑「单台外推」，任何需要「跨设备学习退化模式」的方法都缺数据。'
      + '如实说明比画一条漂亮的预测曲线有价值。</div>'
    + '</div></div>';

  html += '<div class="card mt">' + sect("要让 RUL 真正可用，缺什么", "落地清单")
    + table(["缺什么", "怎么补", "优先级"], [
        ["真实失效记录",
         '<span class="mini">维修结论里已有 <span class="mono">rootCause</span> / '
           + '<span class="mono">effective</span>，但缺「失效时间点」与「失效模式」标注；'
           + '需在工单完成时记录属突发还是渐变</span>',
         '<span class="pill b-red">P0</span>'],
        ["设备额定参数",
         '<span class="mini">转速偏离用全局 1500 rpm 判定，需加 '
           + '<span class="mono">ratedSpeed</span> 字段（见设备档案页）</span>',
         '<span class="pill b-red">P0</span>'],
        ["同型号分组",
         '<span class="mini">按 <span class="mono">model</span> 分组做相似性匹配；'
           + '当前 8 台分属 8 个型号，无同型号对照</span>',
         '<span class="pill b-yellow">P1</span>'],
        ["退化模型选型",
         '<span class="mini">先用线性外推做基线，有失效数据后再对比指数 / 幂律</span>',
         '<span class="pill b-yellow">P1</span>'],
      ])
    + '</div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 归因诊断（shap）
// ══════════════════════════════════════════════════════════════════════
function shapBody(){
  const samples = allSamples().slice().sort((a, b) =>
    String(b.measuredAt).localeCompare(String(a.measuredAt)));
  const abnormal = samples.find(s => s.vibrationMmS >= 9 || s.temperatureC >= 90)
    || samples.find(s => s.vibrationMmS >= 6 || s.temperatureC >= 70)
    || samples[0];
  const attr = abnormal ? attributeSample(abnormal) : null;

  let html = pageHdr("归因诊断",
    "把健康分拆回每个指标的贡献 · 当前用「解析分解」，不是 SHAP",
    '<span class="tag tag-plan">演进中</span>');

  html += noticePlan("<b>关键区分</b>：SHAP 是<b>博弈论意义的 Shapley 值</b>，"
    + "要求有可解释的模型与背景数据集，并满足局部准确性、缺失性、一致性三条公理。"
    + "本系统的规则引擎是<b>线性加权 + 硬上限</b>的确定性函数，"
    + "其分解可以<b>直接解析写出</b>（权重 × 截断比值），根本不需要 SHAP——"
    + "算出来的就是真值，不是近似。<br>"
    + "所以本页做两件<b>都成立</b>的事：① 对现有规则引擎做<b>精确分解</b>"
    + "（下面的瀑布图，真实数据真实算）；② 如实说明「什么时候才真的需要 SHAP」——"
    + "换成树模型或神经网络之后。");

  html += '<div class="grid g4 mt">'
    + kpi("cyan", "当前归因方式", "解析分解", "规则引擎是确定性函数，可精确拆解")
    + kpi("purple", "SHAP 适用时机", "换模型之后", "树模型 / 神经网络才需近似归因")
    + kpi(abnormal ? "red" : "dim", "分解样本",
        abnormal ? fmtNum(abnormal.vibrationMmS, 1) + " mm·s⁻¹" : "-",
        abnormal ? abnormal.equipmentId + " · " + fmtTimeSec(abnormal.measuredAt) : "无样本")
    + kpi(attr ? "yellow" : "dim", "分解得分", attr ? attr.score : "-",
        attr && attr.cap !== null
          ? (attr.cap < attr.rawScore ? "触上限 " + attr.cap + "，已生效" : "触上限 " + attr.cap + "，未生效")
          : "未触上限")
    + '</div>';

  html += '<div class="grid g-3-2 mt">'
    + '<div class="card">' + sect("指标贡献瀑布图（真实分解）",
        abnormal ? abnormal.equipmentId + " · " + fmtTimeSec(abnormal.measuredAt) : "")
    + (attr
        ? '<div class="wfall">'
          + PLAN_METRICS.map(m => {
              const key = m.ak;
              const pen = attr.penalties[key];
              const r = attr.ratios[key];
              if (pen === undefined || r === undefined) return "";
              const w = Math.min(100, pen / 40 * 100);
              const col = pen >= 40 ? "var(--red)" : pen > 0 ? "var(--yellow)" : "var(--line2)";
              return '<div class="wfall-row"><span class="wl">' + h(m.zh) + '</span>'
                + '<span class="wtrack"><span class="wbar" style="width:' + w + '%;background:'
                + col + '"></span></span>'
                + '<span class="wv" style="color:' + (pen > 0 ? col : "var(--dim2,#5f7391)") + '">'
                + (pen > 0 ? "−" : "") + h(fmtNum(pen, 1)) + '</span></div>'
                + '<div class="mini" style="margin:-4px 0 2px 83px">'
                + 'ratio ' + h(fmtNum(r, 3)) + ' × 权重 ' + h(PLAN_WEIGHTS[key])
                + ' → 扣分 ' + h(fmtNum(pen, 1)) + '</div>';
            }).join("")
          + '<div class="wfall-total"><span class="wl">健康分</span>'
          + '<span style="flex:1"></span>'
          + '<span class="wv" style="color:var(--red)">' + h(attr.score) + '</span></div>'
          + '</div>'
          + '<div class="mini mt" style="line-height:1.8">'
          + '<b>分解是精确的</b>：健康分 = 100 − Σ(权重 × clamp(ratio, 0, 1))。'
          + '本次扣分合计 ' + h(fmtNum(attr.penaltySum, 1)) + '，'
          + '故未触上限时应为 <span class="mono">100 − ' + h(fmtNum(attr.penaltySum, 1))
          + ' = ' + h(attr.rawScore) + '</span>。'
          + (attr.cap !== null
              ? '但存在 ratio ≥ ' + (attr.anyTrip ? PLAN_TRIP_RATIO : PLAN_ALARM_RATIO)
                + ' 的指标，触发严重度上限 ' + h(attr.cap) + '。'
                + (attr.cap < attr.rawScore
                    ? '加权和 ' + h(attr.rawScore) + ' 高于上限，故被<b>压到 '
                      + h(attr.score) + '</b>——这就是为什么「加权和」与「最终得分」会对不上：'
                      + '<b>不是算错，是设计如此</b>，单项极端异常不能被其它正常项平均掉。'
                    : '本次加权和 ' + h(attr.rawScore) + ' 本就低于上限，'
                      + '上限<b>未真正生效</b>，最终得分仍是加权和 ' + h(attr.score) + '。'
                      + '（上限是「天花板」而非「地板」——它只会往下压，不会往上抬。）')
              : '本次未触严重度上限，最终得分即加权和。')
          + '<br>另注意 <b>ratio 可以为负</b>（低于正常线），此时扣分取 0——'
          + '所以指标都好时不会产生负扣分（没有加分项），100 分就是上界。'
          + '</div>'
        : emptyBox("无可用样本", "需先有一批真实遥测"))
    + '</div>'

    + '<div class="card">' + sect("分解公式", "与 scoring.py 一致")
    + '<div class="mini" style="line-height:1.95;font-family:Consolas,Menlo,monospace">'
    + 'ratio&nbsp;&nbsp;&nbsp;= (value − normal) / (full − normal)<br>'
    + 'penalty&nbsp;= weight × clamp(ratio, 0, 1)<br>'
    + 'raw&nbsp;&nbsp;&nbsp;&nbsp;= 100 − Σ penalty<br>'
    + 'score&nbsp;&nbsp;&nbsp;= min(raw, cap)<br><br>'
    + 'cap = 39.9&nbsp;&nbsp;&nbsp;若任一 ratio ≥ 1.5<br>'
    + 'cap = 59.9&nbsp;&nbsp;&nbsp;若任一 ratio ≥ 1.0<br>'
    + 'cap = 无上限&nbsp;&nbsp;否则'
    + '</div>'
    + table(["指标", "权重", "ratio 公式"], [
        ["振动", '<span class="mono">40%</span>',
         '<span class="mono mini">(v − 3.0) / 3.0</span>'],
        ["温度", '<span class="mono">25%</span>',
         '<span class="mono mini">(t − 70) / 20</span>'],
        ["电流", '<span class="mono">20%</span>',
         '<span class="mono mini">(c − 15) / 15</span>'],
        ["转速", '<span class="mono">15%</span>',
         '<span class="mono mini">|rpm − 1500| / 1500</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">这是<b>线性可加</b>结构——'
      + '所以每一项的贡献可以唯一确定，不存在 SHAP 要解决的'
      + '「贡献如何在特征间分配」的歧义。<br>'
      + '<b>但硬上限打破了可加性</b>：一旦触发 cap，各项扣分之和不再等于总分差。'
      + '此时即使用 SHAP 也会得到「贡献和 ≠ 输出」——'
      + '这是 SHAP 的已知局限（对含硬阈值的模型不满足局部准确性）。'
      + '本页选择<b>如实展示原始扣分与最终得分两个数</b>，而不是强行让它们相等。</div>'
    + '</div></div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("什么时候才真的需要 SHAP")
    + table(["模型类型", "归因方式", "需要 SHAP 吗"], [
        ["规则加权（当前）", '<span class="mini">解析分解，精确</span>',
         '<span class="pill b-green">不需要</span>'],
        ["逻辑回归 / 线性模型", '<span class="mini">系数 × 特征值</span>',
         '<span class="pill b-green">不需要</span>'],
        ["决策树 / 随机森林 / XGBoost",
         '<span class="mini">有全局重要度，但缺样本级归因</span>',
         '<span class="pill b-yellow">需要（TreeSHAP 有精确算法）</span>'],
        ["神经网络 / LSTM-AE", '<span class="mini">无解析形式</span>',
         '<span class="pill b-red">需要（KernelSHAP / DeepSHAP，且是近似）</span>'],
      ])
    + '<div class="mini mt">所以本页的正确交付顺序是：<b>先有模型，再有 SHAP</b>。'
      + '在没有非线性模型之前上 SHAP，属于为了用工具而用工具——'
      + '算出来的值还不如解析分解精确。</div>'
    + '</div>'

    + '<div class="card">' + sect("可解释性方法可靠性", "选型注意")
    + '<div class="li"><div class="lt"><div class="l1">SHAP 的一致性 '
      + '<span class="pill b-green">有理论保证</span></div>'
      + '<div class="l2">满足一致性公理：某特征贡献变大时，其 Shapley 值不会反而变小。'
      + 'LIME 不满足这一点。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">对含硬阈值的模型会失真 '
      + '<span class="pill b-yellow">已知局限</span></div>'
      + '<div class="l2">本系统的严重度上限（cap）就是这类不连续点。'
      + 'SHAP 假设函数在背景分布上可积，遇到硬截断会出现「贡献和 ≠ 输出」。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">背景数据集会改变结论 '
      + '<span class="pill b-yellow">易被忽视</span></div>'
      + '<div class="l2">SHAP 值是相对背景集的期望，换背景集结果就变。'
      + '报告 SHAP 时必须同时报告背景集。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">别用「特征重要度」代替归因 '
      + '<span class="pill b-red">常见误用</span></div>'
      + '<div class="l2">全局重要度回答「哪个特征整体重要」，'
      + '不回答「这一次为什么报警」——运维要的是后者。</div></div></div>'
    + '</div></div>';

  const eqId = abnormal ? abnormal.equipmentId : richestEq();
  const disc = eqId ? anomalyDiscords(eqId, 6) : null;
  html += '<div class="card mt">' + sect("温度时段热力（真实遥测）",
      eqId ? eqId + " · 最近 " + (disc ? disc.n : 0) + " 个样点" : "")
    + (disc ? planHeatHtml(disc.series, disc.times, 55, 100) : emptyBox("样本不足"))
    + '<div class="legend mt"><span><i style="background:var(--red)"></i>≥ 100℃</span>'
    + '<span><i style="background:var(--yellow)"></i>≥ 78℃</span>'
    + '<span><i style="background:var(--cyan)"></i>≥ 66℃</span>'
    + '<span><i style="background:rgba(57,210,255,.28)"></i>&lt; 66℃</span></div>'
    + '<div class="mini mt" style="line-height:1.8">着色分档端点 55 / 100℃ 仅用于'
      + '<b>视觉分档</b>；判定健康分用的是 scoring.py 的 70 / 90 阈值，'
      + '两者不可混用。每格是一个真实样点，鼠标悬停显示时间与数值。</div>'
    + '</div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 知识库助手（rag）
// ══════════════════════════════════════════════════════════════════════
function ragBody(){
  const done = (state.orders || []).filter(o => o.status === "COMPLETED");
  const withConcl = done.filter(o => o.conclusion && o.conclusion.rootCause);
  const warns = state.warnings || [];

  let html = pageHdr("知识库助手",
    "检索历史工单与维修结论 · 生成维修建议草稿",
    '<span class="tag tag-plan">演进中</span>');

  html += noticePlan("<b>演进中 · 尚未实现</b> —— 本页是<b>信息设计</b>，"
    + "不提供可用的问答（页内输入框已禁用，因为后端没有检索接口）。"
    + "但它列出的<b>语料统计是真的</b>：每条「可入库条数」都是从真实表里数出来的，"
    + "能直接看出这个 RAG 到底有没有料。<br>"
    + "<b>边界声明</b>：助手只做检索与草稿，<b>不参与健康分与预警判定</b>——"
    + "数值判断必须由可复算的规则或经过验证的模型给出；"
    + "生成内容一律标注「草稿，需人工复核」。");

  html += '<div class="grid g4 mt">'
    + kpi("purple", "知识条目", "0", "规划中，尚无向量库")
    + kpi(withConcl.length ? "green" : "dim", "可作语料的维修结论", withConcl.length,
        "已完成工单中带 rootCause 的条数")
    + kpi("dim", "手册页数", "-", "无数据源，未接入")
    + kpi("dim", "未复核草稿", "0", "功能未实现")
    + '</div>';

  html += '<div class="grid g-3-2 mt">'
    + '<div class="card">' + sect("对话式检索", "交互示意（输入已禁用）")
    + '<div style="background:var(--panel2);border:1px solid var(--line);border-radius:8px;'
      + 'padding:12px;margin-bottom:10px">'
      + '<div class="mini" style="margin-bottom:7px">工 · 提问示例</div>'
      + '<div style="font-size:13px">EQ-000001 主轴轴承振动超标，历史上是怎么处理的？</div>'
      + '</div>'
    + '<div style="background:rgba(168,107,255,.07);border:1px solid rgba(168,107,255,.3);'
      + 'border-radius:8px;padding:12px">'
      + '<div class="mini" style="margin-bottom:7px;color:var(--purple)">AI · 检索结果</div>'
      + (withConcl.length
          ? '<div style="font-size:13px;line-height:1.8">根据 ' + withConcl.length
            + ' 条真实维修结论，以下记录与本问题相关：</div>'
            + '<div style="font-size:12.5px;line-height:1.9;margin-top:8px">'
            + '<b class="mono">' + h(withConcl[0].orderId) + '</b> '
            + '<span class="mini">（已完成）</span><br>'
            + '<span class="mini">根本原因：</span>' + h(withConcl[0].conclusion.rootCause) + '<br>'
            + '<span class="mini">处理措施：</span>' + h(withConcl[0].conclusion.measures) + '<br>'
            + '<span class="mini">效果：</span>'
            + h(withConcl[0].conclusion.effective ? "有效" : "无效")
            + (withConcl[0].conclusion.downtimeMinutes
                ? '，停机 ' + h(withConcl[0].conclusion.downtimeMinutes) + ' 分钟' : '')
            + '</div>'
          : '<div style="font-size:13px">暂无带完整结论文本的已完成工单，无可检索语料。</div>')
      + '<div class="mini mt" style="line-height:1.7;border-top:1px solid var(--line);padding-top:8px">'
      + '<b>这不是模型生成的</b>——是对真实数据的<b>直接引用</b>'
      + '（把维修结论字段原文列出）。真正的 RAG 会做向量检索 + 生成，'
      + '本环境没有 embedding 服务与外网，故不假装。</div>'
      + '</div>'
    + '<div style="display:flex;gap:8px;margin-top:10px">'
      + '<input disabled placeholder="功能未实现 —— 需先建向量库" '
      + 'style="flex:1;background:var(--bg2);border:1px solid var(--line);'
      + 'color:var(--dim2,#5f7391);border-radius:6px;padding:8px 10px;font-size:12.5px">'
      + '<button class="btn" disabled>发送</button></div>'
    + '</div>'

    + '<div class="card">' + sect("知识从哪里来", "真实计数")
    + table(["来源", "真实条数", "可入库", "说明"], [
        ["已闭环历史工单", '<span class="mono">' + done.length + '</span>',
         '<span class="pill b-' + (done.length ? "green" : "dim") + '">' + done.length + '</span>',
         '<span class="mini">C <span class="mono">work_order</span> 中 status=COMPLETED</span>'],
        ["维修结论（根因 / 措施 / 有效性）", '<span class="mono">' + withConcl.length + '</span>',
         '<span class="pill b-' + (withConcl.length ? "green" : "red") + '">'
           + withConcl.length + '</span>',
         '<span class="mini">最有价值的语料：有根因、有措施、有效果判定</span>'],
        ["预警记录", '<span class="mono">' + warns.length + '</span>',
         '<span class="pill b-' + (warns.length ? "green" : "dim") + '">' + warns.length + '</span>',
         '<span class="mini">B <span class="mono">warning</span>；含疑似故障与建议措施</span>'],
        ["设备手册 PDF", '<span class="mono">-</span>',
         '<span class="pill b-dim">待录入</span>',
         '<span class="mini">无数据源，需人工上传</span>'],
        ["作业指导书 SOP", '<span class="mono">-</span>',
         '<span class="pill b-dim">待录入</span>',
         '<span class="mini">无数据源</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>一句实话</b>：完整维修结论只有 ' + withConcl.length + ' 条'
    + '（另有 ' + warns.length + ' 条预警可作为弱语料）。'
    + '这个规模做不出有意义的 RAG——检索出来只有一两条，'
    + '和直接看工单列表没区别。<br>'
    + '<b>但语料是从业务流程里长出来的，不是买来的</b>：'
    + '每完成一次维修并认真填写结论，语料就多一条。'
    + '所以本页真正的价值是指出这个缺口与补法，而不是展示一个问答框。</div>'
    + '</div></div>';

  html += '<div class="grid g3 mt">'
    + '<div class="card">' + sect("为什么不直接用通用大模型")
    + '<div class="li"><div class="lt"><div class="l1">幻觉无法接受 '
      + '<span class="pill b-red">致命</span></div>'
      + '<div class="l2">维修建议若编造出「不存在的备件型号」或「错误的扭矩值」，'
      + '会造成实际损失。这不是「效果差一点」的问题。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">私有语料不在训练集 '
      + '<span class="pill b-yellow">必然</span></div>'
      + '<div class="l2">本厂设备型号、历史故障、老师傅经验都不在公开训练数据里。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">可追溯是硬需求 '
      + '<span class="pill b-cyan">审计要求</span></div>'
      + '<div class="l2">每条建议必须能指向具体的历史工单或手册页，否则无法追责与复核。</div></div></div>'
    + '<div class="mini mt">所以要用 RAG（检索增强）而不是直接问模型：'
      + '<b>先检索出真实记录，再让模型组织语言</b>。</div>'
    + '</div>'

    + '<div class="card">' + sect("技术方案要点")
    + '<div class="li"><div class="lt"><div class="l1">① 向量化与索引</div>'
      + '<div class="l2">工单按「设备型号 + 故障描述」分块；中文 embedding 模型量化；'
      + '存本地向量库（chromadb / faiss，纯 CPU 可跑）。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">② 检索策略</div>'
      + '<div class="l2">混合检索：向量相似度 + 关键词（设备号、故障词）过滤，'
      + '避免「语义相近但设备不同」的误召回。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">③ 生成与引用</div>'
      + '<div class="l2">强制要求模型输出引用编号；无引用不得成文；'
      + '无检索结果时明确回答「无相关记录」而<b>不编造</b>。</div></div></div>'
    + '<div class="li"><div class="lt"><div class="l1">④ 边界与免责</div>'
      + '<div class="l2">不接入健康评估与预警判定链路；所有输出标注「草稿」；'
      + '维修人员复核后方可用于工单。</div></div></div>'
    + '</div>'

    + '<div class="card">' + sect("效果怎么衡量", "指标定义")
    + table(["指标", "定义", "目标"], [
        ["引用准确率", '<span class="mini">引用确实支持结论的比例</span>',
         '<span class="mono" style="color:var(--green)">≥ 95%</span>'],
        ["无据生成率", '<span class="mini">无检索结果仍编造答案的比例</span>',
         '<span class="mono" style="color:var(--red)">&lt; 2%</span>'],
        ["召回率 Recall@5", '<span class="mini">正确工单出现在前 5 条的比例</span>',
         '<span class="mono" style="color:var(--green)">≥ 85%</span>'],
        ["人工采纳率", '<span class="mini">工程师实际采用建议的比例</span>',
         '<span class="pill b-dim">观察指标</span>'],
        ["省时", '<span class="mini">查历史 vs 直接提问的耗时差</span>',
         '<span class="pill b-dim">观察指标</span>'],
      ])
    + '<div class="mini mt">前两项是<b>安全指标</b>（不达标不上线），'
      + '后三项是价值指标（用于论证投入产出）。'
      + '<b>当前一个都测不了</b>——没有实现，也没有标注数据。'
      + '列出目标口径是为了后续验收时有据可依。</div>'
    + '</div></div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 模型管理与双轨对账（models）
// ══════════════════════════════════════════════════════════════════════
function modelsBody(){
  const evs = state.evaluations || [];
  const versions = {};
  evs.forEach(e => {
    const v = e.modelVersion || "unknown";
    versions[v] = (versions[v] || 0) + 1;
  });
  const warns = state.warnings || [];
  const orderByWarning = {};
  (state.orders || []).forEach(o => { if (o.warningId) orderByWarning[o.warningId] = o; });

  const linked = warns.filter(w => w.linkedOrderId);
  const resolved = warns.filter(w => w.status === "RESOLVED");
  const warnWithOrder = Object.keys(orderByWarning).length;
  const withConcl = resolved.filter(w => {
    const o = orderByWarning[w.warningId];
    return o && o.conclusion && o.conclusion.result;
  });

  let html = pageHdr("模型管理与双轨对账",
    "模型版本追溯 · 规则轨与业务轨的一致性核对");

  html += noticeInfo("本页<b>已实现</b>（不是规划页）：对账全部使用真实表——"
    + "B 的 <span class=\"mono\">health_evaluation.model_version</span>、"
    + "B 的 <span class=\"mono\">warning</span>、C 的 <span class=\"mono\">work_order</span>，"
    + "三方交叉验证预警从建立到闭环的每一步是否都有对应记录。"
    + "「影子模式」部分尚未实现，已明确标注。");

  html += '<div class="grid g4 mt">'
    + kpi("cyan", "模型版本数", Object.keys(versions).length,
        Object.keys(versions).join(" · ") || "-")
    + kpi("green", "评估记录", evs.length, "B health_evaluation 真实条数")
    + kpi(warnWithOrder ? "green" : "dim", "预警回填工单",
        linked.length + " / " + warns.length, "linkedOrderId 非空的比例")
    + kpi(resolved.length === withConcl.length ? "green" : "yellow",
        "闭环有结论可查", withConcl.length + " / " + resolved.length,
        resolved.length === withConcl.length ? "全部有维修结论"
          : (resolved.length - withConcl.length) + " 条经自动闭环关闭（设计如此）")
    + '</div>';

  html += '<div class="card mt">' + sect("双轨对账表", "三方交叉验证")
    + table(["对账项", "规则轨（B 规则引擎）", "业务轨（C 工单）", "结论"], [
        ["预警 → 工单", '<span class="mini">' + warns.length + ' 条预警</span>',
         '<span class="mini">' + warnWithOrder + ' 个工单带 warningId</span>',
         warns.length === warnWithOrder
           ? '<span class="pill b-green">一致</span>'
           : '<span class="pill b-yellow">差异 ' + Math.abs(warns.length - warnWithOrder) + '</span>'],
        ["工单 → 回填", '<span class="mini">' + linked.length + ' 条 linkedOrderId</span>',
         '<span class="mini">' + warnWithOrder + ' 条可对上</span>',
         linked.length === warnWithOrder
           ? '<span class="pill b-green">一致</span>'
           : '<span class="pill b-red">有悬空引用</span>'],
        ["闭环 → 结论", '<span class="mini">' + resolved.length + ' 条 RESOLVED</span>',
         '<span class="mini">' + withConcl.length + ' 条带 conclusion</span>',
         resolved.length === withConcl.length
           ? '<span class="pill b-green">一致</span>'
           : '<span class="pill b-yellow">' + (resolved.length - withConcl.length)
             + ' 条经「设备恢复自动闭环」关闭，无维修结论</span>'],
        ["模型版本",
         '<span class="mini">' + (Object.keys(versions)
           .map(v => v + " (" + versions[v] + ")").join(", ") || "无") + '</span>',
         '<span class="mini">评估记录逐条带 modelVersion</span>',
         Object.keys(versions).length <= 1
           ? '<span class="pill b-green">单一版本，可追溯</span>'
           : '<span class="pill b-yellow">多版本共存</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>第 3 行为什么允许不一致</b>：本系统有两条预警闭环路径——'
    + '① 维修结论 RECOVERED 经 C-INT-05 回流；'
    + '② 设备恢复正常后 B 在评估到 LOW 时主动 RESOLVE（自动闭环）。'
    + '第 ② 条不产生维修结论，所以「RESOLVED 预警数」本来就可能大于'
    + '「有结论的工单数」。<b>这不是缺陷，但对账时必须知道这个解释</b>，'
    + '否则会误判为数据不一致。</div>'
    + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("模型版本台账", "来自真实评估记录")
    + table(["模型版本", "评估条数", "首次出现", "最近出现"], Object.keys(versions).map(v => {
        const vs = evs.filter(e => (e.modelVersion || "unknown") === v)
          .map(e => e.evaluatedAt).filter(Boolean).sort();
        return ['<span class="mono">' + h(v) + '</span>',
                '<span class="mono">' + versions[v] + '</span>',
                '<span class="mono mini">' + h(vs.length ? fmtTimeSec(vs[0]) : "-") + '</span>',
                '<span class="mono mini">' + h(vs.length ? fmtTimeSec(vs[vs.length-1]) : "-")
                  + '</span>'];
      }), { emptyText: "暂无评估记录" })
    + '<div class="mini mt" style="line-height:1.8">模型版本写在<b>每条评估记录上</b>'
      + '（而非只写在配置里），这样才能回答「这条 30.7 分是哪个版本算出来的」。'
      + '换模型后可对比新旧版本在同一批数据上的分数差异——'
      + '这是模型治理的前提，没有版本号就无法审计历史结论。</div>'
    + '</div>'

    + '<div class="card">' + sect("影子模式（未实现）", "模型上线的安全措施")
    + noticePlan("<b>尚未实现</b> —— 本系统当前是<b>单轨</b>："
      + "规则引擎直接产出评估与预警。影子模式指新模型与规则<b>并行跑</b>、"
      + "只记录不干预，对比一段时间后再决定是否切换。"
      + "这是模型上线的必备措施，但<b>现在没有第二个模型</b>，所以谈不上影子。")
    + table(["阶段", "规则轨", "模型轨", "状态"], [
        ["当前", '<span class="pill b-green">产出决策</span>',
         '<span class="pill b-dim">不存在</span>', '<span class="mini">单轨运行</span>'],
        ["影子", '<span class="pill b-green">产出决策</span>',
         '<span class="pill b-yellow">并行计算，仅记录</span>', '<span class="mini">未实现</span>'],
        ["灰度", '<span class="pill b-green">主决策</span>',
         '<span class="pill b-cyan">部分设备试用</span>', '<span class="mini">未实现</span>'],
        ["切换", '<span class="pill b-dim">降级保底</span>',
         '<span class="pill b-green">产出决策</span>',
         '<span class="mini">需先证明模型优于规则</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">切换判据应是'
      + '「在<b>同一批历史数据</b>上，模型的误报率与漏报率都优于规则」，'
      + '而不是「模型更新」。没有这个对比，切换就是拿生产环境做实验。</div>'
    + '</div></div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 数据质量与漂移（drift）
// ══════════════════════════════════════════════════════════════════════
function driftBody(){
  const dq = realDataQuality();
  const irregularTotal = dq ? dq.intervalStats.reduce((s, x) => s + x.irregular, 0) : 0;

  let html = pageHdr("数据质量与漂移监控",
    "输入数据质量检查 · 模型退化预警 · " + (dq ? dq.samples : 0) + " 条真实样本",
    '<span class="tag tag-plan">部分实现</span>');

  html += noticeInfo("<b>本页的质量检查项是真的</b> —— 缺失率、越界值、重复记录、"
    + "采样间隔稳定性，全部对 " + (dq ? dq.samples : 0) + " 条真实遥测<b>当场计算</b>，"
    + "不是填的示意数字。<br>"
    + "<b>漂移监控（PSI）标为不可用，因为在本环境里它没有意义</b>："
    + "演示种子数据每台设备的值几乎恒定（标准差 0.06~1.3），"
    + "PSI 的分箱在这种数据上会退化——实测跑出来<b>全部远大于常规阈值 1.0</b>"
    + "（即「严重漂移，需重训」），但同一批数据用规则引擎评估健康分 94.7、风险 LOW。"
    + "两个结论不可能同时为真，说明是<b>算法假设不成立</b>导致的假警报。"
    + "所以本页<b>不展示 PSI 数字</b>，只说明它需要什么条件才可用。");

  html += '<div class="grid g4 mt">'
    + kpi(dq && dq.missingRate === 0 ? "green" : "yellow", "数据完整率",
        dq ? fmtNum(100 - dq.missingRate, 2) + "%" : "-",
        "缺失 " + (dq ? dq.missing : 0) + " / " + (dq ? dq.cells : 0) + " 个样本格")
    + kpi("dim", "特征漂移 PSI", "不可用", "演示数据近恒定，分箱退化（见上方说明）")
    + kpi(dq && dq.dupIds === 0 ? "green" : "red", "重复记录", dq ? dq.dupIds : 0,
        "按 sampleId 去重检查")
    + kpi(dq && dq.outOfRange === 0 ? "green" : "red", "越物理范围", dq ? dq.outOfRange : 0,
        "温度 -20~400℃ / 振动 0~200 / 电流 0~500 / 转速 0~50000")
    + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("数据质量检查项", "全部当场计算")
    + table(["检查项", "结果", "说明"], [
        ["缺失值率",
         dq ? '<span class="mono" style="color:'
           + (dq.missingRate === 0 ? "var(--green)" : "var(--yellow)") + '">'
           + fmtNum(100 - dq.missingRate, 2) + '%</span>' : "-",
         '<span class="mini">' + (dq ? dq.cells : 0) + ' 个样本格中缺 '
           + (dq ? dq.missing : 0) + ' 个。A 的遥测入口已做契约校验，缺字段无法入库</span>'],
        ["数值越界",
         dq ? '<span class="mono" style="color:'
           + (dq.outOfRange === 0 ? "var(--green)" : "var(--red)") + '">'
           + dq.outOfRange + '</span>' : "-",
         '<span class="mini">超出物理合理范围。注入工作台只允许预设值，故为 0</span>'],
        ["重复记录",
         dq ? '<span class="mono" style="color:'
           + (dq.dupIds === 0 ? "var(--green)" : "var(--red)") + '">'
           + dq.dupIds + '</span>' : "-",
         '<span class="mini">按 <span class="mono">sampleId</span> 检查；'
           + 'A 有幂等记录表兜底</span>'],
        ["采样间隔稳定",
         '<span class="mono" style="color:'
           + (irregularTotal === 0 ? "var(--green)" : "var(--yellow)") + '">'
           + (irregularTotal === 0 ? "稳定" : irregularTotal + " 处波动") + '</span>',
         '<span class="mini">偏差 &gt; 10% 记为不规则。逐设备明细见右表</span>'],
        ["单位一致性", '<span class="mono" style="color:var(--green)">100%</span>',
         '<span class="mini">契约固定单位（℃ / mm·s⁻¹ / A / rpm），'
           + '无单位字段故不可能不一致</span>'],
        ["特征漂移 PSI", '<span class="pill b-dim">不可用</span>',
         '<span class="mini">需每台设备有足够方差的连续数据；演示库不满足</span>'],
      ])
    + '</div>'

    + '<div class="card">' + sect("采样间隔明细", "逐设备")
    + table(["设备", "样本", "中位数", "最小", "最大", "不规则"],
        dq ? dq.intervalStats.map(s => {
          const fm = v => v >= 60 ? fmtNum(v / 60, 0) + " min" : fmtNum(v, 0) + " s";
          return [
            '<span class="mono mini">' + h(s.eq) + '</span>',
            '<span class="mono mini">' + s.samples + '</span>',
            '<span class="mono mini">' + fm(s.medianSec) + '</span>',
            '<span class="mono mini" style="'
              + (s.minSec < 1 ? "color:var(--yellow)" : "") + '">' + fm(s.minSec) + '</span>',
            '<span class="mono mini" style="'
              + (s.maxSec > s.medianSec * 3 ? "color:var(--yellow)" : "") + '">'
              + fm(s.maxSec) + '</span>',
            '<span class="mono mini" style="color:'
              + (s.irregular ? "var(--yellow)" : "var(--green)") + '">' + s.irregular + '</span>',
          ];
        }) : [], { emptyText: "无样本" })
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>这张表暴露了真实情况</b>：种子数据是每小时一条（中位数 3600 s），'
    + '但注入过异常的设备最小间隔只有几秒、最大间隔十几小时——'
    + '因为演示注入的样点挤在同一秒，中间又隔了跨天空档。'
    + '这是<b>演示数据的固有特征</b>，不是采集故障。'
    + '真实产线的采样应严格等间隔，这里的「不规则」是注入操作造成的。</div>'
    + '</div></div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("为什么这一页对工业场景特别重要")
    + noticeWarn("在消费互联网，模型效果下降 5% 通常只是转化率波动；"
      + "<b>在工业运维，模型效果下降 5% 可能意味着漏掉一次真实故障，"
      + "代价是非计划停机。</b>所以漂移监控不是「加分项」，而是上线前置条件。")
    + '<div class="timeline">'
    + '<div class="tl"><div class="tt">① 数据层 — 入库前校验物理范围</div>'
      + '<div class="td">异常样本打标而非直接丢弃；本页「数值越界」就是它的输出。</div></div>'
    + '<div class="tl warn"><div class="tt">② 特征层 — PSI / KS 每日计算，超阈告警</div>'
      + '<div class="td"><b>未实现</b>，且需先解决本环境数据方差不足的问题。</div></div>'
    + '<div class="tl warn"><div class="tt">③ 模型层 — 影子对账一致率跌破阈值自动回退</div>'
      + '<div class="td"><b>未实现</b>（单轨运行，无影子模型可对账）。</div></div>'
    + '</div>'
    + '<div class="mini mt"><b>关键设计</b>：三层防线都只管告警，<b>不自动改配置</b>——'
      + '是否重训、是否切换由人决定。自动化决策在缺乏验证数据时会放大错误。</div>'
    + '</div>'

    + '<div class="card">' + sect("PSI 需要什么条件才可用")
    + table(["条件", "为什么", "本环境满足吗"], [
        ["基准窗口有足够方差",
         '<span class="mini">PSI 按分箱比较分布；若基准数据近似常量，'
           + '样本全落进同一箱，任何微小扰动都会让 PSI 爆表</span>',
         '<span class="pill b-red">否（sd 0.06~1.3）</span>'],
        ["窗口样本量足够",
         '<span class="mini">经验要求每箱 ≥ 5% 样本、总样本 ≥ 1000</span>',
         '<span class="pill b-red">否（每台 72~81 条）</span>'],
        ["分布本身有实际波动",
         '<span class="mini">产线负荷会变、环境温度会变——真实数据天然有分布</span>',
         '<span class="pill b-red">否（种子值人工恒定）</span>'],
        ["明确「基准」与「当前」切分",
         '<span class="mini">PSI 是两窗口比较，切分点业务上要有意义（如换料 / 换工艺）</span>',
         '<span class="pill b-yellow">可定义但无数据支撑</span>'],
      ])
    + noticeWarn("<b>实测证据</b>：对 8 台设备的前后半段算 PSI，"
      + "振动 / 温度 / 电流全部 <b>&gt; 1.0</b>（按常规阈值属「严重漂移，需重训」）。"
      + "但同一批数据用 B 的规则引擎评估，健康分 94.7、风险 LOW。"
      + "两个结论不可能同时为真。<b>如果页面把这个数字画成红色告警，就是在骗人。</b>")
    + '</div></div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 数据集与特征（dataset）
// ══════════════════════════════════════════════════════════════════════
function datasetBody(){
  const done = (state.orders || []).filter(o => o.status === "COMPLETED");
  const withConcl = done.filter(o => o.conclusion
    && o.conclusion.effective !== undefined && o.conclusion.effective !== null);
  const warns = state.warnings || [];

  const features = [
    { name:"vib_rms", type:"float", src:"telemetry.vibrationMmS", win:"即时", usable:true,
      note:"振动有效值 —— 规则引擎第一权重项（40%）" },
    { name:"vib_mean_1h", type:"float", src:"派生", win:"1h 滑动", usable:true,
      note:"1 小时均值" },
    { name:"vib_std_1h", type:"float", src:"派生", win:"1h 滑动", usable:true,
      note:"1 小时标准差（波动性）" },
    { name:"vib_slope_24h", type:"float", src:"派生", win:"24h 回归", usable:true,
      note:"24 小时趋势斜率 —— trend.py 已在算（trendRatePerDay）" },
    { name:"temp_mean_1h", type:"float", src:"telemetry.temperatureC", win:"1h 滑动", usable:true,
      note:"温度均值" },
    { name:"temp_slope_24h", type:"float", src:"派生", win:"24h 回归", usable:true,
      note:"温度爬升速率" },
    { name:"curr_mean_1h", type:"float", src:"telemetry.currentA", win:"1h 滑动", usable:true,
      note:"电流均值" },
    { name:"rpm_dev", type:"float", src:"telemetry.rotationalSpeedRpm", win:"即时", usable:true,
      note:"相对额定 1500 rpm 的偏离；需 ratedSpeed 才准确" },
    { name:"hist_fail_count", type:"int", src:"work_order 汇总", win:"全历史", usable:true,
      note:"历史故障次数" },
    { name:"days_since_service", type:"int", src:"work_order 汇总", win:"全历史", usable:true,
      note:"距上次维修天数" },
    { name:"future_fail_7d", type:"int", src:"标签", win:"未来 7 天", usable:false,
      note:"预测目标（标签）—— 当前无真实失效记录，无法构造" },
  ];
  const usableN = features.filter(f => f.usable).length;

  let html = pageHdr("数据集与特征管理",
    "训练数据版本化 · 特征定义一致性 · 防训练 / 推理穿越",
    '<span class="tag tag-plan">演进中</span>');

  html += noticePlan("<b>尚未实现数据集管理</b> —— 本页解决的是 ML 工程里"
    + "最隐蔽的一类 bug：<b>训练 / 推理特征穿越（Training-Serving Skew）</b>。"
    + "训练时用了「未来才知道」的特征，离线指标很漂亮，上线就废。<br>"
    + "<b>但特征定义表是真的</b>：下面 " + features.length + " 个特征里，"
    + usableN + " 个的来源字段<b>在当前契约里都已存在</b>（可立即派生），"
    + "只有标签 <span class=\"mono\">future_fail_7d</span> 缺数据——"
    + "因为系统还没有真实失效记录。这个区分很重要："
    + "<b>「特征能不能算」和「标签有没有」是两个不同的缺口</b>，"
    + "前者工程上已具备条件，后者需要业务流程先跑起来。");

  html += '<div class="grid g4 mt">'
    + kpi("purple", "数据集版本", "0", "规划中（无版本管理表）")
    + kpi("cyan", "可立即派生的特征", usableN + " / " + features.length,
        "来源字段在现有契约中已存在")
    + kpi(withConcl.length ? "green" : "red", "标签样本", withConcl.length + " 条工单",
        "来自维修结论的 effective 字段")
    + kpi("yellow", "穿越风险点", "1", "标签字段若误入推理特征即穿越")
    + '</div>';

  html += '<div class="card mt">' + sect("特征定义表", "训练与推理必须共用同一份定义")
    + table(["特征名", "类型", "来源", "窗口", "实时可用", "说明"], features.map(f => [
        '<span class="mono">' + h(f.name) + '</span>',
        '<span class="mini">' + h(f.type) + '</span>',
        '<span class="mono mini">' + h(f.src) + '</span>',
        '<span class="mini">' + h(f.win) + '</span>',
        f.usable ? '<span class="pill b-green">可用</span>'
                 : '<span class="pill b-red">仅训练</span>',
        '<span class="mini">' + h(f.note) + '</span>',
      ]))
    + noticeWarn("<b>穿越检查</b>：<span class=\"mono\">future_fail_7d</span> "
      + "是预测目标，<b>绝不能出现在推理特征中</b>。"
      + "系统应做静态检查——推理时读取的特征列表中若含标注为「仅训练」的字段，"
      + "直接启动失败。<br>"
      + "这条规则听起来多余，但它是 ML 上线事故里最高频的一类："
      + "训练脚本为了「特征丰富」顺手把标签的近邻字段也塞进去了，"
      + "离线 AUC 0.99，上线后和随机猜没区别。")
    + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("标签来源", "零额外成本")
    + noticeInfo("<b>最大优势</b>：维修记录天然构成监督标签，无需人工标注。"
      + "工单里的 <span class=\"mono\">rootCause</span>（根因）、"
      + "<span class=\"mono\">measures</span>（措施）、"
      + "<span class=\"mono\">effective</span>（是否有效）就是现成的训练数据。")
    + table(["标签", "来源字段", "可用样本"], [
        ["故障 vs 正常", '<span class="mono mini">evaluation.riskLevel</span>',
         '<span class="mono">' + (state.evaluations || []).length + '</span>'],
        ["故障类型", '<span class="mono mini">warning.suspectedFault</span>',
         '<span class="mono">' + warns.length + '</span>'],
        ["维修是否有效", '<span class="mono mini">work_order.conclusion.effective</span>',
         '<span class="mono">' + withConcl.length + '</span>'],
        ["剩余寿命", '<span class="mini">需构造（下次故障 − 上次维修）</span>',
         '<span class="mono">0</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">'
    + '「故障 vs 正常」有 ' + (state.evaluations || []).length + ' 条评估记录可用，'
    + '但<b>类别极不平衡</b>——绝大多数是 LOW，HIGH/CRITICAL 只是注入的少数几次。'
    + '真实故障标注（<span class="mono">effective</span>）只有 ' + withConcl.length
    + ' 条，样本量远不足以训练监督模型。'
    + '<b>所以短期内该走无监督路线</b>（见异常检测页），'
    + '监督标签先积累。</div>'
    + '</div>'

    + '<div class="card">' + sect("数据飞轮", "为什么它能转起来")
    + '<div class="timeline">'
    + '<div class="tl ok"><div class="tt">维修记录 → 训练标签</div>'
      + '<div class="td">每次维修填的根因与措施，自动成为标注数据。</div></div>'
    + '<div class="tl ok"><div class="tt">→ 模型迭代</div>'
      + '<div class="td">更多标注 → 模型更准 → 预警更精准。</div></div>'
    + '<div class="tl ok"><div class="tt">→ 更准的预警 → 更多维修记录 → …</div>'
      + '<div class="td">闭环自增强。</div></div>'
    + '</div>'
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>为什么这个飞轮能转起来</b>：因为业务闭环（预警 → 工单 → 维修 → 结论回写）'
    + '已经跑通了。数据不是「额外去采集」的，而是业务运行的副产品。'
    + '这也是本项目相比「纯算法 demo」的实质差别——'
    + '算法可以随时换，但数据管线与业务闭环是护城河。</div>'
    + '</div></div>';

  html += '<div class="card mt">' + sect("数据集版本管理（规划）", "需要记录什么")
    + table(["要记录的内容", "为什么", "优先级"], [
        ["数据快照版本",
         '<span class="mini">用 DVC 或时间戳目录固化；否则「上周的模型」再也复现不出来</span>',
         '<span class="pill b-red">P1</span>'],
        ["特征列表 + 标签定义",
         '<span class="mini">与代码一起版本化，保证训练 / 推理一致</span>',
         '<span class="pill b-red">P1</span>'],
        ["切分策略",
         '<span class="mini">时序数据必须按<b>时间</b>切分，不能随机切——'
           + '随机切会让未来信息泄漏进训练集</span>',
         '<span class="pill b-red">P1</span>'],
        ["样本量与类别分布",
         '<span class="mini">记录每类样本数，便于判断模型是否被多数类主导</span>',
         '<span class="pill b-yellow">P2</span>'],
        ["预处理参数",
         '<span class="mini">归一化均值 / 方差必须存档，推理时用同一套</span>',
         '<span class="pill b-yellow">P2</span>'],
      ])
    + '<div class="mini mt" style="line-height:1.8">'
    + '<b>最容易被忽略的是第 3 行</b>。本系统的数据是<b>时序</b>的，'
    + '若按常规的随机划分，同一个异常段的相邻样本会同时出现在训练集和测试集里，'
    + '测试指标会虚高到荒谬的程度。正确做法是按时间切分，'
    + '并保证异常段整体落在同一侧。</div>'
    + '</div>';

  return html;
}

// ══════════════════════════════════════════════════════════════════════
// 页面注册
// ══════════════════════════════════════════════════════════════════════
/** 演进页共用的数据装载：设备 / 遥测窗口 / 评估历史 / 预警 / 工单 */
async function planLoadCore(){
  await loadCore();
  await Promise.all([
    loadAllTelemetryWindows(),
    ensureEvalHistory(),
  ]);
}

registerPage("anomaly", {
  async load(){ await planLoadCore(); return null; },
  render(){ return anomalyBody(); },
});

registerPage("rul", {
  async load(){ await planLoadCore(); return null; },
  render(){ return rulBody(); },
});

registerPage("shap", {
  async load(){ await planLoadCore(); return null; },
  render(){ return shapBody(); },
});

registerPage("rag", {
  async load(){ await planLoadCore(); return null; },
  render(){ return ragBody(); },
});

registerPage("models", {
  async load(){ await planLoadCore(); return null; },
  render(){ return modelsBody(); },
});

registerPage("drift", {
  async load(){ await planLoadCore(); return null; },
  render(){ return driftBody(); },
});

registerPage("dataset", {
  async load(){ await planLoadCore(); return null; },
  render(){ return datasetBody(); },
});
