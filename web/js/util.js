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
  const el = document.createElement("div");
  el.className = "toast " + (type || "info"); el.textContent = msg;
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function log(action, detail, ok){
  const box = $("log");
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
