/* 视图切换：平台外壳（#shell）与登录页（#view-login）互斥显示。
   页面内部不再各自是一个 <section class="view">——路由渲染进 #content，
   由 platform.js 的 route() 决定渲染哪个页面。 */
"use strict";

function showView(name){
  state.view = name;
  const shell = document.getElementById("shell");
  const login = document.getElementById("view-login");
  if (name === "login") {
    if (shell) shell.style.display = "none";
    if (login) login.style.display = "flex";
  } else {
    if (login) login.style.display = "none";
    if (shell) shell.style.display = "flex";
  }
}
