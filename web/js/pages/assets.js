/* 设备资产台账 —— A GET /api/v1/equipment 真实数据
   筛选：状态 / 产线 / 健康度区间 / 搜索；点击行进入详情。 */
"use strict";

(function () {
  registerPage("assets", {
    load: async function () {
      if (!state.equipment || !state.equipment.length) await loadEquipment();
      if (!Object.keys(state.healthMap).length) await loadLatestEvaluations();
    },

    render: function (ctx) {
      const all = state.equipment || [];
      if (!all.length) {
        return pageHdr("设备资产台账", "全厂关键设备的档案、状态与健康度")
          + emptyBox("还没有设备数据",
              "确认 A 服务（:8101）已启动；种子数据会在首次启动时写入 8 台设备");
      }

      // ---- 筛选条件（来自 state.filter，保持跨渲染稳定）----
      const f = state.filter = state.filter || { status: "", line: "", health: "", kw: "" };
      const lines = Array.from(new Set(all.map(e => e.productionLineId).filter(Boolean))).sort();

      const rows = all.filter(function (e) {
        if (f.status && e.currentStatus !== f.status) return false;
        if (f.line && e.productionLineId !== f.line) return false;
        if (f.kw) {
          const hay = (e.equipmentId + " " + e.name + " " + (e.location || "")).toLowerCase();
          if (hay.indexOf(f.kw.toLowerCase()) < 0) return false;
        }
        const ev = latestEvalOf(e.equipmentId);
        const score = ev ? ev.healthScore : null;
        if (f.health === "good" && !(score !== null && score >= 80)) return false;
        if (f.health === "watch" && !(score !== null && score >= 60 && score < 80)) return false;
        if (f.health === "bad" && !(score !== null && score < 60)) return false;
        return true;
      });

      // ---- KPI ----
      const running = all.filter(e => e.currentStatus === "RUNNING").length;
      const maintaining = all.filter(e => e.currentStatus === "MAINTAINING").length;
      const stopped = all.filter(e => e.currentStatus === "STOPPED").length;
      const trial = all.filter(e => e.currentStatus === "TRIAL_RUNNING").length;
      const scores = all.map(e => { const ev = latestEvalOf(e.equipmentId); return ev ? ev.healthScore : null; })
        .filter(v => v !== null);
      const avg = scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length) : null;

      let html = pageHdr("设备资产台账", "全厂 " + all.length + " 台关键设备的档案、状态与健康度",
        '<button class="btn btn-ghost" onclick="assetsExport()">⇩ 导出 CSV</button>');

      html += noticeLive("数据来源：真实接口 — A <span class=\"mono\">GET /api/v1/equipment?page=&amp;size=</span>（已实现）。"
        + "支持按状态、产线、健康度区间筛选；设备状态由 EquipmentStatusChanged 事件驱动，"
        + "A 服务在 <span class=\"mono\">simulate</span> 与内部遥测入口维护。");

      html += '<div class="grid g6 mt">'
        + kpi("cyan", "设备总数", all.length, lines.length + " 条产线")
        + kpi("green", "运行中", running, "可正常排产")
        + kpi("red", "维修中", maintaining, "占用维修产能")
        + kpi("gray", "已停机", stopped, "含计划停机")
        + kpi("purple", "试运行", trial, "未验收产能")
        + kpi(avg === null ? "dim" : (avg >= 80 ? "green" : avg >= 60 ? "yellow" : "red"),
            "平均健康度", avg === null ? "—" : avg.toFixed(1), "阈值 80 / 60")
        + '</div>';

      // ---- 筛选器 ----
      html += '<div class="card mt"><div class="li" style="flex-wrap:wrap;gap:10px">'
        + '<input id="flt-kw" class="mini" style="flex:1;min-width:180px;background:var(--bg2);border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:7px 10px" placeholder="设备编号 / 名称 / 位置" value="' + h(f.kw) + '">'
        + '<select id="flt-status" style="background:var(--bg2);border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:7px 10px">'
        + '<option value="">全部状态</option>'
        + EQ_STATUSES.map(c => '<option value="' + c + '"' + (f.status === c ? " selected" : "") + '>' + enumZh("equipmentStatus", c) + '</option>').join("")
        + '</select>'
        + '<select id="flt-line" style="background:var(--bg2);border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:7px 10px">'
        + '<option value="">全部产线</option>'
        + lines.map(l => '<option value="' + h(l) + '"' + (f.line === l ? " selected" : "") + '>' + h(l) + '</option>').join("")
        + '</select>'
        + '<select id="flt-health" style="background:var(--bg2);border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:7px 10px">'
        + '<option value="">健康度：全部</option>'
        + '<option value="good"' + (f.health === "good" ? " selected" : "") + '>健康（≥80）</option>'
        + '<option value="watch"' + (f.health === "watch" ? " selected" : "") + '>关注（60–79）</option>'
        + '<option value="bad"' + (f.health === "bad" ? " selected" : "") + '>异常（&lt;60）</option>'
        + '</select>'
        + '<button class="btn" onclick="assetsResetFilter()">重置</button>'
        + '<span class="mini" style="margin-left:auto">共 ' + rows.length + ' 条</span>'
        + '</div></div>';

      // ---- 表格 ----
      html += '<div class="card mt">' + equipmentTableHtml(rows) + '</div>';

      // ---- 分布 ----
      const byLine = {};
      all.forEach(e => { const k = e.productionLineId || "未分类"; byLine[k] = (byLine[k] || 0) + 1; });
      const byStatus = {};
      all.forEach(e => { byStatus[e.currentStatus] = (byStatus[e.currentStatus] || 0) + 1; });

      html += '<div class="grid g2 mt">';
      html += '<div class="card">' + sect("按产线分布", lines.length + " 条")
        + bars(Object.keys(byLine).sort().map(k => ({ label: k, value: byLine[k] })), "info", " 台")
        + '</div>';
      html += '<div class="card">' + sect("按状态分布", "")
        + bars(Object.keys(byStatus).map(k => ({
            label: enumZh("equipmentStatus", k), value: byStatus[k], tone: enumTone("equipmentStatus", k),
          })), null, " 台")
        + '</div></div>';

      // ---- 健康度排行 ----
      const ranked = all.map(function (e) {
        const ev = latestEvalOf(e.equipmentId);
        return { eq: e, ev: ev, score: ev ? ev.healthScore : null };
      }).filter(r => r.score !== null).sort((a, b) => a.score - b.score).slice(0, 5);

      if (ranked.length) {
        html += '<div class="card mt">' + sect("健康度排行", "后 " + ranked.length + " 名 · 重点关注")
          + '<div class="tbl-wrap"><table><thead><tr>'
          + '<th style="width:52px">排名</th><th>设备</th><th style="width:90px">健康度</th>'
          + '<th style="width:150px">主要风险指标</th><th>建议</th></tr></thead><tbody>'
          + ranked.map(function (r, i) {
              const ev = r.ev;
              const tone = enumTone("riskLevel", ev.riskLevel);
              return '<tr onclick="navigate(\'eq/' + h(r.eq.equipmentId) + '\')" style="cursor:pointer">'
                + '<td class="mono">' + (i + 1) + '</td>'
                + '<td><span class="mono">' + h(r.eq.equipmentId) + '</span> '
                + '<span class="mini">' + h(r.eq.name || "") + '</span></td>'
                + '<td><span class="pill b-' + tone + '">' + r.score.toFixed(1) + '</span></td>'
                + '<td class="mini">' + h(ev.suspectedFault || "—") + '</td>'
                + '<td class="mini">' + h(ev.recommendedAction || "—") + '</td></tr>';
            }).join("")
          + '</tbody></table></div></div>';
      }

      return html;
    },

    after: function () {
      wireFilterInputs();
    },
  });

  function wireFilterInputs() {
    const f = state.filter;
    const kw = $("flt-kw");
    if (kw) {
      kw.oninput = function () { f.kw = kw.value; };
      kw.onkeydown = function (e) { if (e.key === "Enter") route(true); };
      kw.onblur = function () { if (f.kw !== kw.value) { f.kw = kw.value; route(true); } };
    }
    const st = $("flt-status");
    if (st) st.onchange = function () { f.status = st.value; route(true); };
    const ln = $("flt-line");
    if (ln) ln.onchange = function () { f.line = ln.value; route(true); };
    const he = $("flt-health");
    if (he) he.onchange = function () { f.health = he.value; route(true); };
  }

  window.assetsResetFilter = function () {
    state.filter = { status: "", line: "", health: "", kw: "" };
    route(true);
  };

  window.assetsExport = function () {
    const rows = state.equipment || [];
    if (!rows.length) { toast("没有可导出的数据", "warn"); return; }
    const head = ["equipmentId", "name", "equipmentType", "productionLineId", "location",
      "currentStatus", "enabled", "version", "healthScore", "riskLevel"];
    const csv = [head.join(",")].concat(rows.map(function (e) {
      const ev = latestEvalOf(e.equipmentId);
      return [e.equipmentId, e.name, e.equipmentType, e.productionLineId, e.location,
        e.currentStatus, e.enabled, e.version,
        ev ? ev.healthScore : "", ev ? ev.riskLevel : ""].map(function (v) {
          const s = v === null || v === undefined ? "" : String(v);
          return s.indexOf(",") >= 0 ? '"' + s + '"' : s;
        }).join(",");
    })).join("\n");

    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "equipment-" + new Date().toISOString().slice(0, 10) + ".csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    toast("已导出 " + rows.length + " 台设备", "success");
    log("EXPORT_EQUIPMENT", rows.length + " 行", true);
  };
})();
