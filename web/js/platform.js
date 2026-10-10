/* ==========================================================================
   platform.js —— 应用框架：侧边栏导航、hash 路由、共享组件与格式化
   --------------------------------------------------------------------------
   真实页面与原型（web/prototype/platform.html）共享同一套设计令牌与类名，
   但本文件面向**真实接口**：每个页面自己声明数据来源，加载失败时给出
   可操作的空状态，而不是显示假数据。

   约定：
     · 枚举中文名一律来自 enums.js（由 tests/test_frontend_enums.py 守着
       与 contracts/shared-enums.json 一致），页面里不写死枚举字符串；
     · 页面通过 registerPage(id, def) 注册，def.render(ctx) 返回 HTML 字符串
       或 DOM 节点，def.load(ctx) 可选地异步取数后再渲染。
   ========================================================================== */
"use strict";

/* ========================= 枚举查询 ========================= */

function enumEntry(group, code){
  const g = ENUMS[group];
  if (!g) return null;
  const e = g[code];
  if (!e) return null;
  return (typeof e === "string") ? { zh: e } : e;
}
function enumZh(group, code, fallback){
  const e = enumEntry(group, code);
  return (e && e.zh) ? e.zh : (fallback !== undefined ? fallback : (code || "—"));
}
function enumTone(group, code){
  const e = enumEntry(group, code);
  return (e && e.tone) ? e.tone : "dim";
}
function toneColor(t){ return (ENUMS.tone && ENUMS.tone[t]) || ENUMS.tone.dim; }

/** 枚举状态标签：中文名 + 语义色，界面上一律用它，不直接显示英文码 */
function tag(group, code){
  if (code === null || code === undefined || code === "") {
    return '<span class="pill b-dim">—</span>';
  }
  return '<span class="pill b-' + enumTone(group, code) + '">'
       + h(enumZh(group, code)) + '</span>';
}
/** 枚举色点（列表里比整块标签更省空间） */
function statusDot(group, code){
  return '<span class="dot d-' + enumTone(group, code) + '"></span>';
}

/* ========================= 转义与格式化 ========================= */

function h(s){
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
  ));
}
function pad2(n){ return String(n).padStart(2, "0"); }

/** ISO 时间 → "MM-DD HH:MM"（列表里用，年份通常无意义） */
function fmtTime(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return pad2(d.getMonth()+1) + "-" + pad2(d.getDate()) + " "
       + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
}
/** ISO 时间 → "MM-DD HH:MM:SS" */
function fmtTimeSec(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return fmtTime(iso) + ":" + pad2(d.getSeconds());
}
/** ISO 时间 → "YYYY-MM-DD" */
function fmtDate(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  return d.getFullYear() + "-" + pad2(d.getMonth()+1) + "-" + pad2(d.getDate());
}
/** 相对时间："3 分钟前" / "2 小时前" / "3 天前" */
function relTime(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  const s = Math.floor((Date.now() - d.getTime()) / 1000);
  if (s < 0) return "刚刚";
  if (s < 60) return s + " 秒前";
  if (s < 3600) return Math.floor(s/60) + " 分钟前";
  if (s < 86400) return Math.floor(s/3600) + " 小时前";
  if (s < 86400*30) return Math.floor(s/86400) + " 天前";
  return fmtDate(iso);
}
/** 分钟 → "2h 14m" / "38 min"，运维场景读时长比读小数自然 */
function fmtMinutes(min){
  if (min === null || min === undefined || isNaN(min)) return "—";
  const m = Math.round(Number(min));
  if (m < 0) return "—";
  if (m < 60) return m + " min";
  const d = Math.floor(m / 1440);
  const hh = Math.floor((m % 1440) / 60);
  const mm = m % 60;
  if (d > 0) return d + "d " + hh + "h";
  return hh + "h " + (mm > 0 ? mm + "m" : "");
}
function fmtNum(v, digits){
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toFixed(digits === undefined ? 1 : digits);
}
function pct(a, b){
  if (!b) return 0;
  return Math.round((a / b) * 1000) / 10;
}

/* ========================= 共享组件 ========================= */

/** KPI 卡：label + 数值 + 脚注。色条由 platform.css 的 .kpi.k-<tone>::after 画 */
function kpi(tone, label, value, foot){
  return '<div class="kpi k-' + tone + '">'
    + '<div class="kl">' + h(label) + '</div>'
    + '<div class="kv">' + value + '</div>'
    + (foot ? '<div class="kf">' + foot + '</div>' : '')
    + '</div>';
}

/** 说明条：live=真实接口已实现 / plan=演进中 / info / warn */
function notice(kind, text){
  const ic = { live:"✓", plan:"◐", info:"i", warn:"⚠" }[kind] || "i";
  return '<div class="notice ' + kind + '"><span class="ni">' + ic + '</span>'
       + '<div class="lt">' + text + '</div></div>';
}
function noticeLive(text){ return notice("live", text); }
function noticePlan(text){ return notice("plan", text); }
function noticeInfo(text){ return notice("info", text); }
function noticeWarn(text){ return notice("warn", text); }

/** 页头：标题 + 副标题 + 右侧操作区 */
function pageHdr(title, sub, right){
  return '<div class="hdr"><div><h1>' + h(title) + '</h1>'
    + (sub ? '<div class="sub">' + sub + '</div>' : '') + '</div>'
    + (right ? '<div class="toolbar">' + right + '</div>' : '') + '</div>';
}

/** 卡片头 */
function sect(title, right){
  return '<div class="hdr" style="margin-bottom:10px"><h2>' + h(title) + '</h2>'
    + (right ? '<div class="mini">' + right + '</div>' : '') + '</div>';
}

function emptyBox(text, hint){
  return '<div class="empty">' + h(text)
    + (hint ? '<div class="mini" style="margin-top:6px">' + hint + '</div>' : '')
    + '</div>';
}

/** 横向进度条，v/max 归一化；tone 决定颜色 */
function bar(v, max, tone, label){
  const w = max > 0 ? Math.max(0, Math.min(100, (v / max) * 100)) : 0;
  return '<div class="bar"><i class="i-' + (tone || "cyan") + '" style="width:'
    + w.toFixed(1) + '%"></i></div>'
    + (label ? '<div class="mini" style="margin-top:3px">' + label + '</div>' : '');
}

/** 迷你趋势图（纯 SVG，不依赖 ECharts）：一条折线 + 可选面积 */
function spark(points, color, opts){
  opts = opts || {};
  const w = opts.w || 120, hh = opts.h || 28;
  const vals = (points || []).filter(v => v !== null && v !== undefined && !isNaN(v));
  if (vals.length < 2) return '<span class="mini">样本不足</span>';
  const mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
  const span = (mx - mn) || 1;
  const dx = w / (vals.length - 1);
  const pts = vals.map((v, i) =>
    (i * dx).toFixed(1) + "," + (hh - 2 - ((v - mn) / span) * (hh - 4)).toFixed(1)
  ).join(" ");
  const c = color || toneColor("cyan");
  let svg = '<svg class="sp" width="' + w + '" height="' + hh + '" viewBox="0 0 '
    + w + ' ' + hh + '" preserveAspectRatio="none">';
  if (opts.fill !== false) {
    svg += '<polygon points="0,' + hh + ' ' + pts + ' ' + w + ',' + hh
         + '" fill="' + c + '" opacity=".13"/>';
  }
  svg += '<polyline points="' + pts + '" fill="none" stroke="' + c
       + '" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  return svg;
}

/** 环形占比图（纯 SVG） */
function donut(percent, color, size, centerText){
  const s = size || 78, r = s/2 - 6, c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, percent || 0));
  const col = color || toneColor("cyan");
  return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 ' + s + ' ' + s + '">'
    + '<circle cx="' + s/2 + '" cy="' + s/2 + '" r="' + r + '" fill="none" '
    + 'stroke="rgba(34,52,80,.9)" stroke-width="7"/>'
    + '<circle cx="' + s/2 + '" cy="' + s/2 + '" r="' + r + '" fill="none" '
    + 'stroke="' + col + '" stroke-width="7" stroke-linecap="round" '
    + 'stroke-dasharray="' + (c*p/100).toFixed(1) + ' ' + c.toFixed(1) + '" '
    + 'transform="rotate(-90 ' + s/2 + ' ' + s/2 + ')"/>'
    + '<text x="50%" y="52%" text-anchor="middle" dominant-baseline="middle" '
    + 'fill="' + col + '" font-size="' + Math.round(s*0.24) + '" font-weight="700">'
    + (centerText !== undefined ? centerText : p + "%") + '</text></svg>';
}

/** 横向条形榜：items = [{label, value, sub}] */
function bars(items, tone, unit){
  if (!items || !items.length) return emptyBox("暂无数据");
  const mx = Math.max.apply(null, items.map(i => i.value)) || 1;
  return items.map(it => '<div style="margin-bottom:9px">'
    + '<div class="li" style="justify-content:space-between;margin-bottom:4px">'
    + '<span class="l1">' + h(it.label) + '</span>'
    + '<span class="lv">' + it.value + (unit || "") + '</span></div>'
    + bar(it.value, mx, it.tone || tone, it.sub)
    + '</div>').join("");
}

/** 表格包装（平台里表格统一加横向滚动，窄屏不破版） */
function table(headers, rows, opts){
  opts = opts || {};
  if (!rows || !rows.length) return emptyBox(opts.emptyText || "暂无数据", opts.emptyHint);
  return '<div class="tbl-wrap"><table><thead><tr>'
    + headers.map(x => '<th>' + h(x) + '</th>').join("")
    + '</tr></thead><tbody>'
    + rows.map(r => '<tr>' + r.map(c => '<td>' + c + '</td>').join("") + '</tr>').join("")
    + '</tbody></table></div>';
}

/** Tab 切换（卡片内：.tabs button + .tabpane） */
function tab(btn, i){
  const box = btn.closest(".card") || btn.closest(".hdrtab");
  if (!box) return;
  box.querySelectorAll(".tabs button").forEach((b, j) => b.classList.toggle("on", j === i));
  box.querySelectorAll(".tabpane").forEach((p, j) => p.classList.toggle("on", j === i));
}
/** 页面级 Tab（顶栏下方切换，切换只影响 #content 内的 .tabpane） */
function ptab(btn, i){
  const bar = btn.closest(".tabs");
  bar.querySelectorAll("button").forEach((b, j) => b.classList.toggle("on", j === i));
  const scope = document.getElementById("content");
  scope.querySelectorAll(":scope > .tabpane, :scope > * > .tabpane")
       .forEach((p, j) => p.classList.toggle("on", j === i));
}

/* ========================= 导航结构 ========================= */
/* 按使用者视角分组，不按微服务 A/B/C/D 分组——后者是技术视角，用户看不懂 */

const NAV = [
  { g:"运营总览", items:[
    { id:"dash",   ic:"◈", n:"驾驶舱首页" },
    { id:"screen", ic:"▣", n:"实时监控大屏", tag:"new" },
  ]},
  { g:"设备管理", items:[
    { id:"assets",  ic:"⚙", n:"设备资产台账" },
    { id:"detail",  ic:"◉", n:"设备详情" },
    { id:"profile", ic:"▤", n:"设备档案铭牌", tag:"plan" },
  ]},
  { g:"健康与预警", items:[
    { id:"health", ic:"♥", n:"健康评估中心" },
    { id:"warns",  ic:"⚠", n:"预警中心", cnt:"warn" },
    { id:"rules",  ic:"⚖", n:"预警规则阈值", tag:"plan" },
  ]},
  { g:"维修管理", items:[
    { id:"kanban", ic:"▦", n:"工单看板 Kanban" },
    { id:"orders", ic:"☰", n:"工单列表", cnt:"order" },
    { id:"odetail",ic:"◫", n:"工单详情时间线" },
  ]},
  { g:"备件管理", items:[
    { id:"spares", ic:"⬢", n:"备件库存" },
    { id:"sreq",   ic:"⇄", n:"领用申请" },
  ]},
  { g:"智能分析", items:[
    { id:"anomaly", ic:"∿", n:"异常检测", tag:"plan" },
    { id:"rul",     ic:"◔", n:"寿命预测 RUL", tag:"plan" },
    { id:"shap",    ic:"◆", n:"归因诊断", tag:"plan" },
    { id:"rag",     ic:"✦", n:"知识库助手", tag:"plan" },
  ]},
  { g:"模型与数据", items:[
    { id:"models",  ic:"◐", n:"模型管理与对账", tag:"plan" },
    { id:"drift",   ic:"≈", n:"数据质量与漂移", tag:"plan" },
    { id:"dataset", ic:"▥", n:"数据集与特征", tag:"plan" },
  ]},
  { g:"系统管理", items:[
    { id:"rbac",   ic:"⚿", n:"组织与权限 RBAC" },
    { id:"notify", ic:"✉", n:"通知中心" },
    { id:"integ",  ic:"⇋", n:"系统集成监控" },
    { id:"audit",  ic:"▤", n:"审计日志" },
  ]},
];

/* 页面元信息：面包屑 + 标题 + 数据来源（顶栏与说明条都用它） */
const PAGE_META = {
  dash:   { crumb:["运营总览","驾驶舱首页"],          title:"驾驶舱首页",     sub:"全厂设备健康态势 · 一屏掌握" },
  screen: { crumb:["运营总览","实时监控大屏"],        title:"实时监控大屏",   sub:"车间级态势 · 适配大屏与移动端" },
  assets: { crumb:["设备管理","设备资产台账"],        title:"设备资产台账",   sub:"全厂关键设备的档案、状态与健康度" },
  detail: { crumb:["设备管理","设备详情"],            title:"设备详情",       sub:"单台设备的遥测、健康、预警与工单" },
  profile:{ crumb:["设备管理","设备档案铭牌"],        title:"设备档案与铭牌", sub:"资产主数据 · 支持二维码铭牌打印与附件管理" },
  health: { crumb:["健康与预警","健康评估中心"],      title:"健康评估中心",   sub:"全厂健康评分 · 风险分级 · 评估历史追溯" },
  warns:  { crumb:["健康与预警","预警中心"],          title:"预警中心",       sub:"全厂预警台账 · 确认 · 转工单 · 闭环追溯" },
  rules:  { crumb:["健康与预警","预警规则阈值"],      title:"预警规则与阈值配置", sub:"评分权重 · 分段阈值 · 自动处置策略" },
  kanban: { crumb:["维修管理","工单看板"],            title:"工单看板",       sub:"按状态列看板视图 · 拖拽式流转（演示：点击卡片进详情）" },
  orders: { crumb:["维修管理","工单列表"],            title:"工单列表",       sub:"表格视图 · 批量筛选与导出" },
  odetail:{ crumb:["维修管理","工单详情"],            title:"工单详情",       sub:"全生命周期时间线 · 动作面板 · 备件与结论" },
  spares: { crumb:["备件管理","备件库存"],            title:"备件库存",       sub:"库存台账 · 安全水位预警 · 领用流水" },
  sreq:   { crumb:["备件管理","领用申请"],            title:"备件领用申请",   sub:"申请 → 审批 → 预留 → 发料 → 关单（8 态流程）" },
  anomaly:{ crumb:["智能分析","异常检测"],            title:"异常检测",       sub:"无监督时序异常检测 · 无需故障标注即可发现未知异常模式" },
  rul:    { crumb:["智能分析","寿命预测 RUL"],        title:"寿命预测（RUL）", sub:"剩余使用寿命区间预测 · 支撑检修排期" },
  shap:   { crumb:["智能分析","归因诊断"],            title:"归因诊断",       sub:"从「健康分 30.7」到「为什么是 30.7」" },
  rag:    { crumb:["智能分析","知识库助手"],          title:"知识库助手",     sub:"检索历史工单与维修手册 · 生成维修建议草稿" },
  models: { crumb:["模型与数据","模型管理与对账"],    title:"模型管理与双轨对账", sub:"规则引擎 vs 影子模型 · 一致率 · 灰度切换" },
  drift:  { crumb:["模型与数据","数据质量与漂移"],    title:"数据质量与漂移监控", sub:"输入数据分布监控 · 模型退化预警" },
  dataset:{ crumb:["模型与数据","数据集与特征"],      title:"数据集与特征管理", sub:"训练数据版本化 · 特征定义一致性" },
  rbac:   { crumb:["系统管理","组织与权限"],          title:"组织与权限",     sub:"7 个角色 · 21 项权限 · 按钮级动态渲染" },
  notify: { crumb:["系统管理","通知中心"],            title:"通知中心",       sub:"多渠道通知 · 模板管理 · 发送记录" },
  integ:  { crumb:["系统管理","系统集成监控"],        title:"系统集成监控",   sub:"服务健康 · 契约一致性 · 事件投递" },
  audit:  { crumb:["系统管理","审计日志"],            title:"审计日志",       sub:"全链路操作留痕 · traceId 追踪" },
};

/* 页面注册表：id -> { render(ctx) 或 load(ctx) } */
const PAGES = {};
function registerPage(id, def){
  PAGES[id] = def;
  return def;
}

/* ========================= 路由 ========================= */

/* 可路由路径 → 页面 id。
   #/eq/EQ-000001 与 #/orders/WO-xxx 这种带参数的路径在这里解析成 ctx.params */
function parseHash(){
  let raw = location.hash.replace(/^#\/?/, "");
  if (!raw) return { id: "dash", params:{} };
  const seg = raw.split("/").filter(Boolean);
  const head = seg[0];
  const aliases = { "":"dash", "eq":"detail", "order":"odetail", "warn":"warns", "sr":"sreq" };
  const id = PAGES[head] ? head : (aliases[head] || head);
  const params = {};
  if (aliases[head] === "detail" || head === "eq") params.equipmentId = seg[1] || null;
  if (aliases[head] === "odetail" || head === "order") params.orderId = seg[1] || null;
  if (head === "warn") params.warningId = seg[1] || null;
  if (head === "sreq" && seg[1]) params.requestId = seg[1];
  return { id, params };
}

function navigate(path, replace){
  const target = "#/" + String(path).replace(/^#?\/?/, "");
  if (replace) history.replaceState(null, "", target);
  else location.hash = target;
  if (replace) route();
}

let _lastRoute = "";
async function route(){
  const { id, params } = parseHash();
  const meta = PAGE_META[id] || { crumb:["",""], title:"页面" };
  const key = id + JSON.stringify(params);
  const content = document.getElementById("content");
  if (!content) return;

  // 面包屑
  const crumb = document.getElementById("crumb");
  if (crumb) {
    crumb.innerHTML = '<span class="cb1">' + h(meta.crumb[0]) + '</span>'
      + '<span class="csep">/</span><span class="cb2">' + h(meta.crumb[1]) + '</span>';
  }

  renderNav(id);

  if (!state.token) { showView("login"); return; }
  showView("app");

  const def = PAGES[id];
  if (!def) {
    content.innerHTML = pageHdr(meta.title)
      + noticePlan("本页尚在规划中。")
      + emptyBox("该页面还没有实现", "可在左侧导航选择已实现的页面");
    return;
  }

  // 同一路由重复触发（如轮询刷新）不重渲染整页，避免输入框失焦
  if (_lastRoute !== key || def.alwaysRender) {
    _lastRoute = key;
    content.innerHTML = '<div class="empty">加载中…</div>';
    try {
      const ctx = { id, params, meta, el: content };
      // load 负责取数、render 负责出串：两者可分开（assets 等页如此），
      // 因此 load 返回 undefined 时还要再问 render 一次。早期只走其中一个分支，
      // 分开写的页面就永远停在"加载中…"（2026-10-10 修复）。
      let out = def.load ? await def.load(ctx) : undefined;
      if (out === undefined && def.render) out = def.render(ctx);
      if (typeof out === "string") content.innerHTML = out;
      else if (out instanceof Node) { content.innerHTML = ""; content.appendChild(out); }
      else if (out === undefined && !def.render) {
        content.innerHTML = pageHdr(meta.title) + noticePlan("本页尚未实现内容渲染。");
      }
    } catch (e) {
      content.innerHTML = pageHdr(meta.title)
        + noticeWarn("页面数据加载失败：" + h(e.message || e))
        + emptyBox("无法渲染本页", "请确认四服务已启动（A 8101 / B 8102 / C 8103 / D 8104），"
          + "或点顶栏「服务地址」检查地址是否正确");
    }
  }
  if (def.after) def.after({ id, params, el: content });
}

function renderNav(activeId){
  const root = document.getElementById("navroot");
  if (!root) return;
  // 详情页高亮它所属的列表页
  const hl = { detail:"assets", odetail:"orders" }[activeId] || activeId;
  root.innerHTML = NAV.map(grp => {
    const items = grp.items.map(it => {
      let cnt = "";
      if (it.cnt === "warn") {
        const n = (state.warnings || []).filter(w =>
          ["OPEN","ACKNOWLEDGED","LINKED_TO_ORDER"].includes(w.status)).length;
        cnt = n ? '<span class="cnt">' + n + '</span>' : "";
      } else if (it.cnt === "order") {
        const n = (state.orders || []).filter(o =>
          !["COMPLETED","CANCELLED"].includes(o.status)).length;
        cnt = n ? '<span class="cnt">' + n + '</span>' : "";
      }
      const beta = it.tag === "plan" ? '<span class="beta">β</span>' : "";
      return '<a class="navi' + (it.id === hl ? ' on' : '') + '" href="#/' + it.id + '">'
        + '<span class="ic">' + it.ic + '</span><span class="nm">' + h(it.n) + '</span>'
        + beta + cnt + '</a>';
    }).join("");
    return '<div class="navgrp">' + h(grp.g) + '<span class="gt"></span></div>' + items;
  }).join("");
}

/* ========================= 顶栏与框架 ========================= */

function renderTopbarUser(){
  const who = document.getElementById("who");
  if (!who) return;
  if (!state.user) { who.innerHTML = ""; return; }
  const u = state.user;
  const role = u.roleCode || (u.roles && u.roles[0]) || "";
  const initial = (u.name || u.username || "?").slice(0, 1);
  who.innerHTML = '<div class="av">' + h(initial) + '</div>'
    + '<div class="nm">' + h(u.name || u.username || "—")
    + '<small>' + h(u.userId || u.username || "") + '</small></div>'
    + '<span class="rolechip">' + h(enumZh("roleCode", role, role || "—")) + '</span>';
}

function toggleSidebar(){
  const sb = document.getElementById("sidebar");
  if (!sb) return;
  sb.classList.toggle("mini");
  try { localStorage.setItem("ims_sidebar_mini", sb.classList.contains("mini") ? "1" : "0"); } catch(e){}
}

function wireFramework(){
  // 侧栏收起状态记忆
  try {
    if (localStorage.getItem("ims_sidebar_mini") === "1") {
      document.getElementById("sidebar").classList.add("mini");
    }
  } catch(e){}
  // 全局搜索：回车跳到设备台账并带上关键词（各页自行读取 state.search）
  const si = document.getElementById("search-input");
  if (si) {
    si.addEventListener("keydown", e => {
      if (e.key !== "Enter") return;
      state.search = si.value.trim();
      navigate("assets");
    });
  }
  window.addEventListener("hashchange", route);
}

/* 页面可读的全局搜索词（由顶栏搜索框写入） */
state.search = "";

/* 侧栏角标随数据变化重绘 */
function refreshNavBadges(){ renderNav((parseHash() || {}).id); }
