/* 轮询与启动（P2-2：单一 5 秒定时器按视图拉取，设备页不再整页轮询看板，
   移除了引用不存在 "detail" 视图的 30 秒兜底定时器） */
"use strict";
/* 轮询：当前路由页若声明了 poll(ctx)，就按 5 秒节奏调它。
   页面用 alwaysRender 或局部刷新自己决定要不要重建 DOM——轮询**不重渲染整页**，
   否则用户正在填的表单会被冲掉。 */
function startPolling(){
  stopPolling();
  state.timer = setInterval(async () => {
    if (!state.token || state.polling) return;   // 上一轮未完成时跳过，防重入堆积
    const r = parseHash() || {};
    const def = PAGES[r.id];
    if (!def || !def.poll) return;
    state.polling = true;
    try {
      // 必须把 params 一起传下去：详情页的 poll 靠 ctx.params.equipmentId
      // 定位设备，漏传会报 "Cannot read properties of undefined (reading 'equipmentId')"。
      await def.poll({ id: r.id, params: r.params || {}, el: document.getElementById("content") });
    }
    catch (e) { console.warn("[polling]", e.message); }
    finally { state.polling = false; }
  }, REFRESH_MS);
}
function stopPolling(){ if (state.timer) { clearInterval(state.timer); state.timer = null; } state.polling = false; }

/* 地址框已存值校验（纯函数，可测）：
   返回 true = 值可保留；false = 与该框服务代号不符，需重置默认。
   规则：取 URL 路径的最后一个字母段，若它恰是 a/b/c/d 之一但不等于
   本框代号（典型：实验时把 D 框填成了 /a），判为填串，自动纠正；
   直连模式（纯 host:port，无路径）与空值不在此列，交给既有逻辑处理。 */
function basebarValueMatchesCode(saved, code){
  if (!saved) return false;
  let path;
  try {
    const u = new URL(saved, location.origin);
    path = u.pathname.replace(/\/+$/, "");
  } catch (e) { return false; }
  if (!path) return true;   // 直连模式（无路径前缀）：不干预
  const last = path.slice(path.lastIndexOf("/") + 1);
  if (/^[a-d]$/.test(last)) return last === code;
  return true;              // 含其他路径的值不干预（不误伤自定义反代）
}

function boot(){
  wireFramework();
  // 服务地址框：同源反代默认（/a /b /c /d，公网零配置可用），
  // 手动改过存 localStorage；公网访问时旧的本机直连值不可达，自动回退同源反代
  (function initBasebar(){
    const hint = $("basebar-hint");
    // file:// 直接双击 html 打开时 hostname 为空串：此时同源反代不可用，
    // 必须允许本机直连地址（否则默认 /a 会解析成 file:///a 必然失败）。
    const pageIsFile = location.protocol === "file:";
    if (hint) {
      hint.title = pageIsFile
        ? "直连模式（file:// 打开）：必须填 http://127.0.0.1:810x；推荐改用 scripts\\start_all.ps1 启动的统一入口 http://127.0.0.1:8888/（零配置）"
        : "同源反代（默认）：nginx :8888 的 /a /b /c /d 前缀；直连模式改为 http://IP:810x（仅服务器本机可用）";
    }
    const pageOriginLocal = pageIsFile || /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
    const directDefaults = { a: "http://127.0.0.1:8101", b: "http://127.0.0.1:8102",
                             c: "http://127.0.0.1:8103", d: "http://127.0.0.1:8104" };
    let corrected = [];
    for (const c of ["a", "b", "c", "d"]) {
      const input = $("base-" + c);
      let saved = localStorage.getItem("ims_base_" + c);
      if (saved && /^https?:\/\/(localhost|127\.0\.0\.1)/.test(saved) && !pageOriginLocal) {
        saved = null;   // 公网浏览器持本机直连地址：必然不可达，回退默认
        corrected.push(c);
      } else if (saved && !basebarValueMatchesCode(saved, c)) {
        saved = null;   // 填串的值（如 D 框存着 /a）：登录会 404，自动纠正
        corrected.push(c);
      }
      if (saved === null && pageIsFile) {
        // file:// 下 HTML 默认值 /a 不可用，改为直连本机端口，双击打开也能直接登录
        input.value = directDefaults[c];
      } else if (saved !== null) input.value = saved;
      input.addEventListener("change", function(){
        localStorage.setItem("ims_base_" + c, this.value.trim());
      });
    }
    if (corrected.length) {
      toast("服务地址框 " + corrected.map(c => c.toUpperCase()).join("/") +
        " 的旧配置有误，已自动恢复同源默认（/a /b /c /d）", "ok");
    }
    const resetBtn = $("basebar-reset");
    if (resetBtn) resetBtn.addEventListener("click", function(){
      for (const c of ["a", "b", "c", "d"]) {
        $("base-" + c).value = pageIsFile ? directDefaults[c] : "/" + c;
        localStorage.removeItem("ims_base_" + c);
      }
      toast(pageIsFile
        ? "服务地址框已恢复默认：http://127.0.0.1:8101~8104（直连）"
        : "服务地址框已恢复默认：/a /b /c /d", "ok");
    });
  })();
  if (typeof echarts === "undefined") {
    toast("ECharts 本地文件未加载成功，图表功能不可用（检查 web/echarts.min.js 是否存在）", "err");
  }
  if (state.token && state.user) enterApp();
  else showView("login");
}
document.addEventListener("DOMContentLoaded", boot);
