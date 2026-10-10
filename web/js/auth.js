/* 登录 / 退出 / 进入应用 */
"use strict";
function fillUser(uid){
  $("login-user").value = uid; $("login-pass").value = "demo123456"; $("login-err").textContent = "";
}

async function login(){
  const username = $("login-user").value.trim();
  const password = $("login-pass").value;
  const btn = $("login-btn"); btn.disabled = true; btn.textContent = "登录中…";
  try {
    const data = await api("d", "/api/v1/auth/login", {
      method:"POST", body:{username, password},
    });
    state.token = data.accessToken;
    state.user = data.user;
    state.sessionExpiredNotified = false;
    localStorage.setItem("ims_token", state.token);
    localStorage.setItem("ims_user", JSON.stringify(state.user));
    enterApp();
  } catch (e) {
    $("login-err").textContent = "登录失败：" + e.message
      + (/404/.test(e.message) ? "（登录接口在 D 服务——检查顶部第 4 个地址框应为 /d，或点\"恢复默认\"）" : "");
  } finally {
    btn.disabled = false; btn.textContent = "登录";
  }
}

function logout(){
  state.token = ""; state.user = null;
  state.sessionExpiredNotified = false;
  localStorage.removeItem("ims_token"); localStorage.removeItem("ims_user");
  stopPolling();
  // P2-6：退出后清空全部业务缓存，避免下一账号看到上一账号的数据
  state.equipment = []; state.warnings = []; state.orders = [];
  state.healthMap = {}; state.latestEvaluation = {}; state.assignees = null;
  state.openEq = null; state.expandedOrder = null; state._openForm = null;
  const warnCard = $("eq-warn-card");
  if (warnCard) warnCard.style.display = "none";
  hideStatus();
  const demo = $("demo-btn");
  if (demo) demo.style.display = "none";
  _lastRoute = "";
  showView("login");
  renderTopbarUser();
}

async function enterApp(){
  $("login-err").textContent = "";
  const demo = $("demo-btn");
  if (demo) demo.style.display = "inline-flex";
  renderTopbarUser();
  // 权限以登录响应为准，但服务端改角色后旧 token 里的权限会过期——
  // 进入应用时静默刷新一次（失败不阻断，permSet() 会退回 state.user.permissions）
  if (typeof loadAccessContext === "function") loadAccessContext();
  // 登录后回到地址栏里的路由（如有人把 #/warns 分享过来），否则进驾驶舱
  if (!location.hash || location.hash === "#/login") {
    navigate("dash", true);
  } else {
    await route();
  }
  startPolling();
}
