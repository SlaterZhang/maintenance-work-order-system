/* ============================================================================
 * 页面：备件库存（#/spares）
 * 数据来源：C GET /api/v1/spare-parts（state.spareParts）
 * 口径：备件独立成模块——库存数量变化只有通过「申请 → 预留 → 发料 → 退料/关单」
 * 这条状态机才发生，不做覆盖式写。app: apps/maintenance/src/domain/state_machine.py
 * 的 SPARE_TRANSITIONS 是唯一权威。
 * ==========================================================================*/

function sparePartOf(id){ return (state.spareParts || []).find(p => p.sparePartId === id) || null; }
function spareName(id){ const p = sparePartOf(id); return p ? p.name + " " + p.specification : id; }
function spareUnit(id){ const p = sparePartOf(id); return p ? p.unit : ""; }

function spareStockTone(p){
  const avail = p.availableQuantity;
  if (avail <= 0) return "red";
  if (avail < p.reorderPoint) return "yellow";
  return "green";
}

/** 领用按钮：库存见底则禁用；低于安全库存则二次确认。
 *  原先"需补货"的备件照样能一键领走，安全水位形同虚设——
 *  至少要让操作者知道自己在动一批已经告急的库存。 */
function issueBtnHtml(p){
  const avail = Number(p.availableQuantity || 0);
  const low = avail < Number(p.reorderPoint || 0);
  if (avail <= 0) {
    return '<button class="btn btn-sm" disabled title="可用库存为 0，请先补货"'
      + ' style="opacity:.45;cursor:not-allowed">领用</button>';
  }
  const warn = low
    ? ' onclick="confirmLowStockIssue(\'' + h(p.sparePartId) + '\',\'' + h(p.name)
      + '\',' + avail + ')"'
    : ' onclick="openCreateSpareRequestModal(null,\'' + h(p.sparePartId) + '\')"';
  return '<button class="btn ' + (low ? 'btn-o' : 'btn-o') + ' btn-sm"' + warn + '>领用</button>';
}

/** 低于安全库存时的领用二次确认 */
function confirmLowStockIssue(partId, name, avail){
  openModal("该备件已低于安全库存",
    '<div class="mini" style="line-height:1.8">'
    + '<b>' + h(name) + '</b>（' + h(partId) + '）当前可用 <b>' + h(avail) + '</b>，'
    + '已低于安全库存水位。<br>继续领用会进一步拉低库存，请确认现场确实急需。'
    + '</div>',
    { width: 460,
      footer: '<button class="btn btn-ghost" onclick="closeModal()">取消</button>'
        + '<button class="btn" onclick="closeModal();openCreateSpareRequestModal(null,\''
        + h(partId) + '\')">仍然领用</button>' });
}

function sparesTableHtml(){
  const kw = (state.spareFilter || {}).kw || "";
  const lowOnly = !!(state.spareFilter || {}).lowOnly;
  let list = state.spareParts || [];
  if (kw) {
    const k = kw.toLowerCase();
    list = list.filter(p => [p.sparePartId, p.name, p.specification]
      .some(v => String(v || "").toLowerCase().includes(k)));
  }
  if (lowOnly) list = list.filter(p => p.availableQuantity < p.reorderPoint);

  const rows = list.map(p => {
    const tone = spareStockTone(p);
    const ratio = p.reorderPoint > 0 ? Math.min(1, p.availableQuantity / (p.reorderPoint * 3)) : 1;
    return [
      '<span class="mono">' + h(p.sparePartId) + '</span>',
      h(p.name) + ' <span class="mini">' + h(p.specification) + '</span>',
      h(p.onHandQuantity) + ' ' + h(p.unit),
      '<b>' + h(p.availableQuantity) + '</b> ' + h(p.unit),
      h(p.reservedQuantity),
      h(p.reorderPoint),
      '<div style="min-width:90px">' + bar(ratio, 1, tone) + '</div>',
      p.availableQuantity < p.reorderPoint
        ? '<span class="pill b-red">需补货</span>'
        : '<span class="pill b-green">正常</span>',
      issueBtnHtml(p),
    ];
  });

  return '<div id="spare-tbl">'
    + table(["备件编码", "名称 / 规格", "在库量", "可用量", "已预留", "安全库存", "水位", "状态", "操作"],
        rows, { emptyText: "无匹配备件", emptyHint: "试试清空关键词或取消「只看告警项」" })
    + '</div>';
}

function applySpareFilter(){
  state.spareFilter = {
    kw: ((document.getElementById("sp-kw") || {}).value || "").trim(),
    lowOnly: !!(document.getElementById("sp-low") || {}).checked,
  };
  return route(true);
}

function toggleLowStock(){
  const c = document.getElementById("sp-low");
  state.spareFilter = Object.assign({}, state.spareFilter, { lowOnly: !!(c && c.checked) });
  return route(true);
}

function sparesBody(){
  const list = state.spareParts || [];
  const low = list.filter(p => p.availableQuantity < p.reorderPoint);
  // 补货缺口 = 各告警项"还差多少才到安全线"之和，即 Σ(reorderPoint - availableQuantity)。
  // 早期这里累加的是 availableQuantity（"还剩多少"），把现存量和缺口搞反了：
  // 同步带 5/15、交流接触器 4/10、变频器 2/3 的真实缺口是 10+6+1=17，页面却显示 11（=5+4+2）。
  const lowGap = low.reduce((s, p) => s + (Number(p.reorderPoint || 0) - Number(p.availableQuantity || 0)), 0);
  const totalAvail = list.reduce((s, p) => s + p.availableQuantity, 0);
  const reserved = list.reduce((s, p) => s + p.reservedQuantity, 0);
  const cats = [...new Set(list.map(p => p.name.split(" ")[0]))];

  let html = pageHdr("备件库存", "库存台账 · 安全水位预警 · 领用流水",
    '<div class="btn-group">'
    + '<button class="btn btn-o btn-sm" onclick="exportSparesCsv()">⇩ 导出 CSV</button>'
    + '<button class="btn btn-p btn-sm" onclick="openCreateSpareRequestModal()">＋ 新建申请</button>'
    + '</div>');

  html += noticeLive("数据来源：真实接口 — C <span class=\"mono\">GET /api/v1/spare-parts</span>（已实现）。"
    + "领用走 <span class=\"mono\">POST /api/v1/work-orders/{orderId}/spare-requests</span> 建申请，"
    + "<span class=\"mono\">POST /api/v1/spare-requests/{requestId}/commands</span> 审批/预留/发料/退料/关单。"
    + "库存采用「申请 → 预留 → 发料 → 扣减」的流水模型，不做覆盖式写——每一次数量变化都有对应流水记录，可对账。");

  // KPI 口径必须写清单位，否则"低于安全库存 3"和"告警项缺口 11"并排放着
  // 会被读成互相矛盾——前者是**条目数**（3 个备件低于水位），
  // 后者是**数量缺口合计**（这 3 项加起来还差 11 个才到安全线），
  // 单位不同、层级不同，分开放并把单位写进副标题。
  html += '<div class="grid g5 mt">'
    + kpi("cyan",  "备件品类", list.length, cats.length + " 个分类")
    + kpi(low.length ? "red" : "green", "低于安全库存", low.length + " 项",
          low.length ? "需立即补货" : "全部充足")
    + kpi("purple", "已预留", reserved, "待发料占用")
    + kpi("yellow", "可用总量", totalAvail, "各备件可用量之和")
    // 单位不写死：告警项可能跨品类（条 / 个 / 台），加总后没有统一单位，
    // 早期写死"个"既算错又串味。这里只报数量，单位由表格逐行给出。
    + kpi("dim",   "补货缺口", lowGap,
          low.length ? low.length + " 项合计缺口 " + lowGap + "（跨品类，仅作补货优先级参考）" : "无需补货")
    + '</div>';

  html += '<div class="card mt"><div class="toolbar">'
    + '<input id="sp-kw" placeholder="备件编码 / 名称 / 规格" style="width:220px" value="'
      + h((state.spareFilter || {}).kw || "") + '">'
    + '<label class="mini" style="display:flex;align-items:center;gap:6px">'
      + '<input type="checkbox" id="sp-low"' + ((state.spareFilter || {}).lowOnly ? " checked" : "")
      + ' onchange="toggleLowStock()"> 只看告警项</label>'
    + '<button class="btn btn-o btn-sm" onclick="applySpareFilter()">查询</button>'
    + '<span class="mini" style="margin-left:auto">'
      + (low.length ? '<span style="color:var(--red)">' + low.length + ' 项低于安全库存</span>'
                    : "库存水位正常")
      + '</span></div>'
    + sparesTableHtml()
    + '</div>';

  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("分类库存分布", "按可用量")
    + bars(list.map(p => ({
        label: p.name, value: p.availableQuantity + p.reservedQuantity,
        tone: spareStockTone(p), sub: p.specification,
      })), null, "")
    + '<div class="mini mt">低于安全库存：'
      + (low.length ? low.map(p => h(p.name) + " " + p.availableQuantity + "/" + p.reorderPoint)
          .join("、") : "无")
      + '</div></div>'
    + '<div class="card">' + sect("领用状态机", "8 态 / 7 个动作")
    + table(["状态", "含义", "可执行动作"], [
        ["PENDING_APPROVAL", "待审批", "APPROVE / REJECT / CANCEL"],
        ["APPROVED", "已批准", "RESERVE / CANCEL"],
        ["RESERVED", "已预留", "ISSUE / CANCEL"],
        ["ISSUED", "已发料", "RETURN / CLOSE"],
        ["PARTIALLY_RETURNED", "部分退料", "RETURN / CLOSE"],
        ["CLOSED", "已关单", "—（终态）"],
        ["REJECTED", "已驳回", "—（终态）"],
        ["CANCELLED", "已取消", "—（终态）"],
      ].map(r => ['<span class="mono mini">' + r[0] + '</span><br>' + tag("spareRequestStatus", r[0]),
                  '<span class="mini">' + r[1] + '</span>',
                  '<span class="mini mono">' + r[2] + '</span>']))
    + '<div class="mini mt">审批 / 预留 / 取消需 <span class="mono">SPARE_APPROVE</span>，'
      + '发料 / 退料 / 关单需 <span class="mono">SPARE_ISSUE</span>，申请需 '
      + '<span class="mono">SPARE_REQUEST</span>——三者分离，避免一个人走完整个流程。</div>'
    + '</div></div>';

  return html;
}

function exportSparesCsv(){
  downloadCsv("spare-parts", ["备件编码", "名称", "规格", "单位", "在库量", "可用量",
    "已预留", "安全库存", "版本"],
    (state.spareParts || []).map(p => [p.sparePartId, p.name, p.specification, p.unit,
      p.onHandQuantity, p.availableQuantity, p.reservedQuantity, p.reorderPoint, p.version]));
}

registerPage("spares", {
  async load(ctx){
    if (!state.spareParts.length) await loadSpareParts();
    return sparesBody();
  },
  async poll(ctx){
    if (!document.getElementById("spare-tbl")) return;
    await loadSpareParts();
    const el = document.getElementById("spare-tbl");
    if (el) el.outerHTML = sparesTableHtml();
  },
});
