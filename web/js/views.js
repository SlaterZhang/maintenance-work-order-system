/* 视图切换与导航 */
"use strict";
function showView(name){
  state.view = name;
  document.querySelectorAll("section.view").forEach(v => v.classList.remove("active"));
  $("view-" + name).classList.add("active");
  document.querySelectorAll("#nav button").forEach(b =>
    b.classList.toggle("active", b.dataset.view === name ||
      (name === "equipment" && b.dataset.view === "dashboard")));
  if (name === "login") {
    const warnCard = $("eq-warn-card");
    if (warnCard) warnCard.style.display = "none";
  }
  if (name === "dashboard") refreshDashboard();
  if (name === "orders") refreshOrders();
}

function wireNav(){
  document.querySelectorAll("#nav button").forEach(b =>
    b.addEventListener("click", () => showView(b.dataset.view)));
}
