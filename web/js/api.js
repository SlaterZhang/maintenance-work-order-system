/* 统一 API 访问层：fetch 封装、Bearer 头、401 会话过期处理（P2-6） */
"use strict";
async function api(svc, path, opts){
  document.getElementById("loading-bar").style.display = "block";
  try {
    opts = opts || {};
    const url = base(svc) + path;
    const headers = Object.assign({"Content-Type":"application/json"}, opts.headers || {});
    let resp;
    try {
      resp = await fetch(url, {
        method: opts.method || "GET", headers, body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch (e) {
      throw new Error("无法连接 " + url.replace(/^https?:\/\//, "").split("/")[0] +
        "（服务未就绪，请检查服务状态）：" + e.message);
    }
    let data = null;
    try { data = await resp.json(); } catch (e) { /* 无响应体 */ }
    if (!resp.ok) {
      // P2-6：带令牌却 401 = 会话过期（JWT 2 小时），统一引导重新登录。
      // 注意只有 401 才算：503（依赖服务不可达，如 D 身份服务连不上）绝不能
      // 当成"登录过期"把用户登出——否则服务端一抖，前端就一直踢人下线。
      if (resp.status === 401 && state.token) handleSessionExpired();
      const msg = (data && (data.message || data.code)) ? (data.message || data.code) : ("HTTP " + resp.status);
      throw new Error(msg);
    }
    return data;
  } finally {
    document.getElementById("loading-bar").style.display = "none";
  }
}

function authHeaders(){
  const h = {};
  if (state.token) h["Authorization"] = "Bearer " + state.token;
  return h;
}

function handleSessionExpired(){
  if (state.sessionExpiredNotified) return;
  state.sessionExpiredNotified = true;
  toast("登录已过期（约 2 小时），请重新登录", "err");
  logout();
}
