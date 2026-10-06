/* 轮询与启动（P2-2：单一 5 秒定时器按视图拉取，设备页不再整页轮询看板，
   移除了引用不存在 "detail" 视图的 30 秒兜底定时器） */
"use strict";
function startPolling(){
  stopPolling();
  state.timer = setInterval(async () => {
    if (!state.token || state.polling) return;   // 上一轮未完成时跳过，防重入堆积
    state.polling = true;
    try {
      if (state.view === "dashboard") await refreshDashboard();
      else if (state.view === "orders") await refreshOrders();
      else if (state.view === "equipment" && state.openEq) {
        await Promise.all([refreshEquipmentDetail(), loadTelemetry()]);
      }
    } finally {
      state.polling = false;
    }
  }, REFRESH_MS);
}
function stopPolling(){ if (state.timer) { clearInterval(state.timer); state.timer = null; } state.polling = false; }

function boot(){
  wireNav();
  wireOrdersEvents();
  // 服务地址框：同源反代默认（/a /b /c /d，公网零配置可用），
  // 手动改过存 localStorage；公网访问时旧的本机直连值不可达，自动回退同源反代
  (function initBasebar(){
    const hint = $("basebar-hint");
    if (hint) hint.title = "同源反代（默认）：nginx :8888 的 /a /b /c /d 前缀；直连模式改为 http://IP:810x（仅服务器本机可用）";
    const pageOriginLocal = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
    for (const c of ["a", "b", "c", "d"]) {
      const input = $("base-" + c);
      let saved = localStorage.getItem("ims_base_" + c);
      if (saved && /^https?:\/\/(localhost|127\.0\.0\.1)/.test(saved) && !pageOriginLocal) {
        saved = null;   // 公网浏览器持本机直连地址：必然不可达，回退默认
      }
      if (saved !== null) input.value = saved;
      input.addEventListener("change", function(){
        localStorage.setItem("ims_base_" + c, this.value.trim());
      });
    }
  })();
  if (typeof echarts === "undefined") {
    toast("ECharts 本地文件未加载成功，图表功能不可用（检查 web/echarts.min.js 是否存在）", "err");
  }
  if (state.token && state.user) enterApp();
  else {
    showView("login");
    const wc = $("eq-warn-card");
    if (wc) wc.style.display = "none";
  }
}
document.addEventListener("DOMContentLoaded", boot);
