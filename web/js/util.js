/* 通用工具：DOM 查询、转义、toast（带降噪）、操作日志、状态条 */
"use strict";
function uuidv4(){
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random()*16|0; return (c==="x" ? r : (r&0x3|0x8)).toString(16);
  });
}
function nowIso(){ return new Date().toISOString(); }
function hhmmss(){ return new Date().toTimeString().slice(0,8); }
function base(svc){ return document.getElementById("base-" + svc).value.trim().replace(/\/+$/,""); }
function $(id){ return document.getElementById(id); }
function esc(s){
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

/* P2-3 toast 降噪：同文案 8 秒内只弹一次（轮询错误不再刷屏） */
const _toastLast = new Map();
function toast(msg, type){
  const now = Date.now();
  const last = _toastLast.get(msg) || 0;
  if (now - last < 8000) return;
  _toastLast.set(msg, now);
  const host = $("toasts");
  if (!host) return;   // 容器缺失时不能抛错，否则会打断调用方的后续步骤
  const el = document.createElement("div");
  el.className = "toast " + (type || "info"); el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function log(action, detail, ok){
  const box = $("log");
  // 不是每个页面都有 #log 面板（工单详情页就没有）。早先这里不判空，
  // 直接 box.querySelector 会抛 TypeError —— 而调用方常把 log() 写在
  // 关键流程中间（如 submitSpareRequest 里 closeModal() 之后），
  // 异常会把后面的 toast、列表刷新、route(true) 全部吃掉：
  // 数据其实提交成功了，页面却毫无反应，用户以为"点了没生效、不能再次申请"。
  if (!box) return;
  if (box.querySelector(".log-t") && box.children.length === 1
      && box.textContent.startsWith("等待操作")) box.innerHTML = "";
  const type = ok === false ? "err" : ok === true ? "succ" : "INFO";
  const tagCls = type === "INFO" ? "tag-INFO" : "tag-" + type;
  const line = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `[${hhmmss()}] <span class="log-tag ${tagCls}">${type}</span>` +
    `<span class="log-act">${esc(action)}</span> ${esc(detail || "")}`;
  box.prepend(line);
  while (box.children.length > 60) box.lastChild.remove();
}

function showStatus(text){
  const bar = $("status-bar");
  if (!text) { bar.style.display = "none"; return; }
  bar.style.display = "flex";
  $("status-text").textContent = text;
}
function hideStatus(){
  $("status-bar").style.display = "none";
}
