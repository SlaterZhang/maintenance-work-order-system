/* ==========================================================================
   modals.js —— 弹窗、确认框、帮助面板
   --------------------------------------------------------------------------
   平台里有几处需要"先问一句再动手"的交互：执行工单动作、停用设备、
   值机注入异常。统一走这里，样式与按键行为一致（Esc 关闭、点遮罩关闭）。
   ========================================================================== */
"use strict";

let _modalStack = [];

/** 通用弹窗：html 为内容，opts.onOpen(el) 可在插入后绑定事件 */
function openModal(title, html, opts){
  opts = opts || {};
  const wrap = document.createElement("div");
  wrap.className = "modal-mask";
  wrap.innerHTML =
    '<div class="modal" style="max-width:' + (opts.width || 560) + 'px">'
    + '<div class="hdr"><h2>' + h(title) + '</h2>'
    + (opts.closable === false ? "" : '<button class="tbtn" data-close>✕</button>')
    + '</div><div class="modal-body">' + html + '</div>'
    + (opts.footer ? '<div class="modal-foot">' + opts.footer + '</div>' : '')
    + '</div>';
  document.body.appendChild(wrap);
  _modalStack.push(wrap);
  wrap.addEventListener("click", e => {
    if (e.target === wrap || e.target.hasAttribute("data-close")) closeModal();
  });
  if (opts.onOpen) opts.onOpen(wrap);
  return wrap;
}
function closeModal(){
  const w = _modalStack.pop();
  if (w) w.remove();
}
function closeAllModals(){
  while (_modalStack.length) closeModal();
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && _modalStack.length) closeModal();
});

/** 确认框：返回 Promise<boolean> */
function confirmBox(title, message, opts){
  opts = opts || {};
  return new Promise(resolve => {
    let done = false;
    const finish = v => { if (!done) { done = true; closeModal(); resolve(v); } };
    const w = openModal(title,
      '<div class="lt" style="font-size:13px;line-height:1.75">' + message + '</div>',
      {
        width: opts.width || 460,
        footer: '<button class="btn btn-g" data-no>取消</button>'
              + '<button class="btn ' + (opts.danger ? "btn-d" : "btn-p") + '" data-yes>'
              + h(opts.okText || "确定") + '</button>',
      });
    w.querySelector("[data-yes]").onclick = () => finish(true);
    w.querySelector("[data-no]").onclick = () => finish(false);
    w.querySelector(".hdr [data-close]")?.addEventListener("click", () => finish(false));
  });
}

/** 提示框（只有一个"知道了"按钮） */
function alertBox(title, message){
  return new Promise(resolve => {
    const w = openModal(title,
      '<div class="lt" style="font-size:13px;line-height:1.75">' + message + '</div>',
      { width: 460, footer: '<button class="btn btn-p" data-ok>知道了</button>' });
    w.querySelector("[data-ok]").onclick = () => { closeModal(); resolve(true); };
  });
}

/** 帮助面板：说明四个服务与演示剧本，答辩时随手可查 */
function showHelp(){
  openModal("使用说明",
    '<div class="lt" style="font-size:13px;line-height:1.8">'
    + '<p><b>这套界面连的是什么？</b><br>'
    + '左侧导航按“使用者视角”分组，每组页面都直接读四个微服务的真实接口：'
    + 'A 设备监测（:8101）、B 故障预警（:8102）、C 维修工单（:8103）、D 身份通知（:8104）。'
    + '页面顶部的说明条会写明本页数据来自哪个服务、哪些字段是真实存在的。</p>'
    + '<p><b>标 β 的页面是什么？</b><br>'
    + '智能分析与模型管理这 7 页属于<b>演进规划</b>：页面里展示的是信息设计与落地路径，'
    + '图表是示意形状而非真实计算结果。这是有意为之——'
    + '把还没做的能力画得和已实现的一样，答辩时会被追问到无法回答。</p>'
    + '<p><b>怎么演示全链路？</b><br>'
    + '进「设备详情」→ 展开「模拟数据注入工作台」→ 点「注入异常（严重）」，'
    + '会依次发生：A 写入异常遥测 → B 评分并建预警 → C 自动建工单 → '
    + '回设备详情可见预警卡片。再点「恢复正常数据」，预警会自动闭环、'
    + '尚未进维修的工单自动结单。</p>'
    + '<p><b>为什么有的按钮是灰的？</b><br>'
    + '每个工单动作都要对应的权限码（如 <span class="mono">WORK_ORDER_ASSIGN</span>）。'
    + '当前登录角色没有该项权限时按钮不可点——这是按权限渲染，'
    + '真正的拦截在服务端，前端隐藏只是体验优化。</p>'
    + '</div>',
    { width: 640, footer: '<button class="btn btn-p" data-close2>知道了</button>' ,
      onOpen: w => w.querySelector("[data-close2]").onclick = () => closeModal() });
}

/** 会话状态面板：轮询/令牌/权限一眼可见，排查"界面不刷新"时有用 */
function showSessionInfo(){
  const u = state.user || {};
  const perms = u.permissions || [];
  openModal("会话与数据状态",
    '<div class="tbl-wrap"><table><tbody>'
    + '<tr><td class="mini">登录身份</td><td>' + h(u.displayName || "—")
    + ' <span class="mono">' + h(u.userId || "") + '</span></td></tr>'
    + '<tr><td class="mini">角色</td><td>' + ((u.roleCodes || []).map(r => tag("roleCode", r)).join(" ") || "—") + '</td></tr>'
    + '<tr><td class="mini">权限数</td><td>' + perms.length + ' 项'
    + (perms.includes("ADMIN_ALL") ? '（含 <span class="mono">ADMIN_ALL</span> 全部权限）' : '') + '</td></tr>'
    + '<tr><td class="mini">令牌类型</td><td>JWT · 有效期约 2 小时</td></tr>'
    + '<tr><td class="mini">轮询间隔</td><td>' + (REFRESH_MS / 1000) + ' 秒（仅当前页面声明了 poll 才拉取）</td></tr>'
    + '<tr><td class="mini">最近刷新</td><td>'
    + (state.lastFetch ? h(new Date(state.lastFetch).toLocaleTimeString()) : "—") + '</td></tr>'
    + '<tr><td class="mini">服务地址</td><td class="mono">'
    + ["a","b","c","d"].map(c => h($("base-" + c).value)).join("<br>") + '</td></tr>'
    + '</tbody></table></div>',
    { width: 560, footer: '<button class="btn btn-g" data-close3>关闭</button>',
      onOpen: w => w.querySelector("[data-close3]").onclick = () => closeModal() });
}
