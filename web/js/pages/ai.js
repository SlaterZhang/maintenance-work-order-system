/* ══════════════════════════════════════════════════════════════════════
 * AI 助手（#/ai）—— 基于全厂实时数据的 AI 问答。
 *
 * 架构：前端组装「全厂知识快照」作为 system 消息 → POST /api/v1/ai/chat
 * （D 服务代理，key 在服务端 ai_config.json，不落前端）→ SSE 流式渲染。
 *
 * 为什么是快照而不是整库：608 个遥测样点全塞进提示词 token 爆炸；
 * 快照只带「台账 + 最新遥测 + 阈值 + 活跃预警 + 进行中工单 + 低库存备件
 * + 最近维修结论」，约一千 token 出头，AI 能回答绝大多数业务问题。
 * ══════════════════════════════════════════════════════════════════════ */

registerPage("ai", {
  async load(ctx){
    await planLoadCore();
    if (!state.spareParts || !state.spareParts.length) {
      try { await loadSpareParts(); } catch (e) { /* 备件不可达不挡聊天 */ }
    }
    return aiHtml();
  },
  after(ctx){ aiBind(); },
});

/* ─────────────────────────── 页面骨架 ─────────────────────────── */

function aiHtml(){
  const head = '<div class="hdr"><div><h1>' + h("AI 助手")
    + hintMark("回答基于全厂实时数据快照（设备台账 / 最新遥测 / 阈值规则 / 活跃预警 / 进行中工单 / 备件库存 / 最近维修结论）。模型与密钥在服务端 ai_config.json 配置，系统管理员可在下方设置区增删模型。")
    + '</h1></div></div>';

  return head
    + '<div class="ai-wrap">'
      + '<div class="ai-main card">'
        + '<div class="ai-msgs" id="ai-msgs"></div>'
        + '<div class="ai-quick" id="ai-quick"></div>'
        + '<div class="ai-inputrow">'
          + '<textarea id="ai-input" rows="2" placeholder="问点什么…（回车发送，Shift+回车换行）"></textarea>'
          + '<button class="btn btn-primary" id="ai-send">发送</button>'
        + '</div>'
      + '</div>'
      + '<div class="ai-side">'
        + '<div class="card">'
          + sect("对话设置", "全员可用")
          + '<div class="field"><label>模型</label><select id="ai-model"></select>'
            + '<span class="mini" id="ai-model-admin"></span></div>'
          + '<div class="field"><label>思考强度</label><select id="ai-thinking"></select></div>'
          + '<label class="chk"><input type="checkbox" id="ai-ctx-on" checked> 注入全厂知识快照</label>'
          + '<div class="mini" id="ai-ctx-stat"></div>'
        + '</div>'
        + '<div class="card" id="ai-admin-card" style="display:none">'
          + sect("模型管理", "仅系统管理员")
          + '<div class="field"><label>模型 ID</label><input id="ai-new-id" placeholder="如 qwen3-max"></div>'
          + '<div class="field"><label>显示名</label><input id="ai-new-name" placeholder="如 Qwen3 Max"></div>'
          + '<label class="chk"><input type="checkbox" id="ai-new-think" checked> 支持思考输出</label>'
          + '<button class="btn btn-primary btn-sm" id="ai-add-model" style="margin-top:8px">添加模型</button>'
          + '<div id="ai-model-list" style="margin-top:10px"></div>'
        + '</div>'
      + '</div>'
    + '</div>';
}

/* ─────────────────────────── 事件绑定 ─────────────────────────── */

function aiBind(){
  const input = document.getElementById("ai-input");
  if (!input) return;
  document.getElementById("ai-send").onclick = () => aiSend();
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); aiSend(); }
  });
  document.getElementById("ai-model").onchange = e => { aiSettings.model = e.target.value; aiSaveLocal(); };
  document.getElementById("ai-thinking").onchange = e => { aiSettings.thinking = e.target.value; aiSaveLocal(); };
  const add = document.getElementById("ai-add-model");
  if (add) add.onclick = () => aiAddModel();
  aiLoadConfig();
  aiGreet();
  aiRenderQuick();
}

/* 本地偏好：模型/思考强度记住上一次选择 */
let aiSettings = { model: null, thinking: null };
function aiSaveLocal(){
  try { localStorage.setItem("ims_ai_settings", JSON.stringify(aiSettings)); } catch (e) {}
}
function aiLoadLocal(){
  try { return JSON.parse(localStorage.getItem("ims_ai_settings") || "{}"); } catch (e) { return {}; }
}

/* ─────────────────────────── 配置加载 ─────────────────────────── */

let aiCfg = null;

async function aiLoadConfig(){
  const local = aiLoadLocal();
  aiSettings = { model: local.model || null, thinking: local.thinking || null };
  try {
    aiCfg = await api("d", "/api/v1/ai/config", { headers: authHeaders() });
  } catch (e) {
    aiCfg = null;
    const msgs = document.getElementById("ai-msgs");
    if (msgs) msgs.innerHTML = '<div class="ai-msg bot"><div class="ai-bubble">AI 服务未连接：'
      + h(e.message) + '<br>请联系管理员检查服务端 <span class="mono">ai_config.json</span>。</div></div>';
    return;
  }
  /* 模型下拉 */
  const sel = document.getElementById("ai-model");
  const prov = (aiCfg.providers || [])[0] || { models: [], defaultModel: null };
  const models = prov.models || [];
  sel.innerHTML = models.map(m =>
    '<option value="' + h(m.id) + '">' + h(m.name || m.id) + "</option>").join("");
  aiSettings.model = models.some(m => m.id === aiSettings.model)
    ? aiSettings.model : (prov.defaultModel || (models[0] && models[0].id));
  if (aiSettings.model) sel.value = aiSettings.model;
  /* 思考强度下拉 */
  const tsel = document.getElementById("ai-thinking");
  const levels = aiCfg.thinkingLevels || {};
  tsel.innerHTML = Object.keys(levels).map(k =>
    '<option value="' + h(k) + '">' + h(levels[k].label || k) + "</option>").join("");
  aiSettings.thinking = levels[aiSettings.thinking] ? aiSettings.thinking
    : (aiCfg.defaultThinking || "normal");
  tsel.value = aiSettings.thinking;
  /* 管理员区 */
  if (aiCfg.isAdmin) {
    document.getElementById("ai-admin-card").style.display = "";
    document.getElementById("ai-model-admin").textContent = "（管理员：可增删）";
    aiRenderModelList();
  }
  aiCtxStat();
}

function aiRenderModelList(){
  const box = document.getElementById("ai-model-list");
  if (!box || !aiCfg) return;
  const prov = (aiCfg.providers || [])[0] || { models: [] };
  box.innerHTML = (prov.models || []).map(m =>
    '<div class="li" style="padding:6px 8px;gap:8px"><b>' + h(m.name || m.id) + "</b>"
    + '<span class="mini mono">' + h(m.id) + "</span>"
    + (m.thinking ? '<span class="pill b-cyan">思考</span>' : "")
    + '<button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="aiDelModel(\'' + h(m.id) + '\')">删除</button>'
    + "</div>").join("");
}

async function aiAddModel(){
  const id = document.getElementById("ai-new-id").value.trim();
  const name = document.getElementById("ai-new-name").value.trim() || id;
  const thinking = document.getElementById("ai-new-think").checked;
  if (!id) { toast("请填写模型 ID", "err"); return; }
  try {
    await api("d", "/api/v1/ai/models", {
      method: "POST", headers: authHeaders(),
      body: JSON.stringify({ model_id: id, name, thinking }),
    });
    toast("模型已添加", "ok");
    document.getElementById("ai-new-id").value = "";
    await aiLoadConfig(); aiRenderModelList();
  } catch (e) { toast("添加失败：" + e.message, "err"); }
}

async function aiDelModel(id){
  const yes = await confirmBox("删除模型", "确定删除模型 <b>" + h(id) + "</b>？");
  if (!yes) return;
  try {
    await api("d", "/api/v1/ai/models/" + encodeURIComponent(id),
      { method: "DELETE", headers: authHeaders() });
    toast("模型已删除", "ok");
    await aiLoadConfig(); aiRenderModelList();
  } catch (e) { toast("删除失败：" + e.message, "err"); }
}

/* ─────────────────────────── 知识快照 ─────────────────────────── */

function aiSnapshot(){
  const eqs = state.equipment || [];
  const warns = (state.warnings || []).filter(w =>
    !["RESOLVED", "CANCELLED"].includes(w.status));
  const orders = (state.orders || []).filter(o =>
    !["COMPLETED", "CANCELLED"].includes(o.status));
  const evs = state.evaluations || [];
  const spares = state.spareParts || [];

  const L = [];
  L.push("你是工业设备智能运维平台的 AI 助手，面向运维工程师与管理者。");
  L.push("回答要具体、可执行；引用数据时注明设备编号。以下是当前全厂实时数据快照：");

  L.push("\n【设备台账】共 " + eqs.length + " 台");
  eqs.slice(0, 12).forEach(e => {
    const t = (state.telemetryMap || {})[e.equipmentId];
    L.push("- " + e.equipmentId + " " + (e.name || "") + "｜产线 " + (e.productionLineId || "—")
      + "｜状态 " + (e.status || "—") + "｜位置 " + (e.location || "—")
      + (e.healthScore != null ? "｜健康 " + e.healthScore : ""));
    if (t) L.push("  最新遥测: 温度 " + t.temperatureC + "℃ / 振动 " + t.vibrationMmS
      + "mm·s⁻¹ / 电流 " + t.currentA + "A / 转速 " + t.rotationalSpeedRpm
      + "rpm（" + (t.createdAt || "") + "）");
  });

  L.push("\n【阈值规则】温度 70/90℃（报警/跳闸）、振动 3.0/6.0 mm·s⁻¹、"
    + "电流 15/30A、转速偏差 5%/15%；健康分 100 起按权重扣（振动40%/温度25%/电流20%/转速15%），"
    + "任一指标进报警区（ratio≥1）健康分≤59.9，进跳闸区（ratio≥1.5）≤39.9。");

  L.push("\n【活跃预警】" + warns.length + " 条");
  warns.slice(0, 10).forEach(w => {
    L.push("- " + w.warningId + " " + w.equipmentId + "｜" + (w.suspectedFault || "")
      + "｜风险 " + (w.riskLevel || "") + "｜状态 " + (w.status || "")
      + "｜建议 " + (w.recommendedAction || "—"));
  });

  L.push("\n【进行中工单】" + orders.length + " 张");
  orders.slice(0, 10).forEach(o => {
    L.push("- " + o.orderId + " " + o.equipmentId + "｜" + (o.title || "")
      + "｜优先级 " + (o.priority || "") + "｜状态 " + (o.status || ""));
  });

  const done = (state.orders || []).filter(o => o.status === "COMPLETED" && o.conclusion
    && (o.conclusion.rootCause || o.conclusion.measures));
  L.push("\n【最近维修结论】（已完成工单 " + done.length + " 张，取最近 5 条）");
  done.slice(0, 5).forEach(o => {
    L.push("- " + o.orderId + " " + o.equipmentId + "｜根因: " + (o.conclusion.rootCause || "—")
      + "｜措施: " + (o.conclusion.measures || "—")
      + "｜" + (o.conclusion.effective ? "有效" : "无效"));
  });

  const low = spares.filter(s => (s.quantity ?? 99) <= (s.reorderPoint ?? 0));
  L.push("\n【备件库存】共 " + spares.length + " 项，低于补货点 " + low.length + " 项");
  low.slice(0, 6).forEach(s => {
    L.push("- " + s.sparePartId + " " + (s.name || "") + "｜库存 " + s.quantity
      + "｜补货点 " + s.reorderPoint);
  });

  L.push("\n回答规则：只基于以上快照回答，数据里没有的就直说「快照中没有该数据」；"
    + "涉及处置建议时给出具体步骤与所需备件；不确定时先反问澄清。");
  return L.join("\n");
}

function aiCtxStat(){
  const el = document.getElementById("ai-ctx-stat");
  if (!el) return;
  const snap = aiSnapshot();
  el.textContent = "快照约 " + Math.round(snap.length / 2.2) + " token · "
    + (state.equipment || []).length + " 台设备 · "
    + (state.warnings || []).filter(w => !["RESOLVED", "CANCELLED"].includes(w.status)).length + " 条活跃预警";
}

/* ─────────────────────────── 对话 ─────────────────────────── */

function aiGreet(){
  const msgs = document.getElementById("ai-msgs");
  if (!msgs) return;
  msgs.innerHTML = '<div class="ai-msg bot"><div class="ai-bubble">你好，我是运维 AI 助手。'
    + "我可以基于全厂实时数据回答：设备状态、异常解读、处置建议、备件与工单情况。"
    + "试试下面的快捷问题，或直接提问。</div></div>";
}

function aiRenderQuick(){
  const box = document.getElementById("ai-quick");
  if (!box) return;
  const QS = ["我的任务是什么？", "现在哪些设备有异常？", "活跃预警该怎么处置？",
              "备件库存有缺口吗？", "最近维修都修了什么？"];
  box.innerHTML = QS.map(q => '<button class="btn btn-ghost btn-sm" data-q="' + h(q) + '">' + h(q) + "</button>").join("");
  box.querySelectorAll("button").forEach(b => b.onclick = () => {
    document.getElementById("ai-input").value = b.getAttribute("data-q");
    aiSend();
  });
}

let aiBusy = false;

async function aiSend(){
  if (aiBusy) return;
  const input = document.getElementById("ai-input");
  const text = (input.value || "").trim();
  if (!text) return;
  const msgs = document.getElementById("ai-msgs");
  input.value = "";
  /* 用户消息 */
  const user = document.createElement("div");
  user.className = "ai-msg user";
  user.innerHTML = '<div class="ai-bubble"></div>';
  user.firstChild.textContent = text;
  msgs.appendChild(user);
  /* 占位 */
  const bot = document.createElement("div");
  bot.className = "ai-msg bot";
  bot.innerHTML = '<div class="ai-bubble"><span class="ai-cursor">▍</span></div>';
  msgs.appendChild(bot);
  msgs.scrollTop = msgs.scrollHeight;
  aiBusy = true;

  const history = aiHistory(msgs);
  const body = {
    messages: [
      { role: "system", content:
        (document.getElementById("ai-ctx-on") && document.getElementById("ai-ctx-on").checked)
          ? aiSnapshot() : "你是工业设备智能运维平台的 AI 助手。" },
      ...history,
      { role: "user", content: text },
    ],
    model: aiSettings.model || undefined,
    thinking: aiSettings.thinking || undefined,
  };

  try {
    const resp = await fetch("/d/api/v1/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (!resp.ok || !resp.body) {
      const d = await resp.json().catch(() => ({}));
      throw new Error(d.detail || ("HTTP " + resp.status));
    }
    await aiConsumeStream(resp.body, bot.firstChild);
  } catch (e) {
    bot.firstChild.innerHTML = '⚠ ' + h(e.message)
      + '<br><span class="mini">请检查 AI 服务连接（服务端 ai_config.json）。</span>';
  }
  aiBusy = false;
  const bubble = bot.firstChild;
  if (!bubble.textContent.trim()) bubble.textContent = "（空回复）";
  msgs.scrollTop = msgs.scrollHeight;
}

/* 历史窗口：保留最近 6 轮，防 token 膨胀 */
function aiHistory(msgs){
  const out = [];
  const nodes = [...msgs.querySelectorAll(".ai-msg")].slice(-13);
  nodes.forEach(n => {
    const isUser = n.classList.contains("user");
    const t = n.querySelector(".ai-bubble").textContent.trim();
    if (!t || t.startsWith("⚠") || t === "（空回复）") return;
    out.push({ role: isUser ? "user" : "assistant", content: t.slice(0, 1200) });
  });
  return out.slice(0, 12);
}


/* ── 简易 Markdown 渲染：表格 / 标题 / 加粗 / 列表 / 行内代码 ──
   先整体 HTML 转义防注入，再按行转换。 */
function mdToHtml(text){
  const esc = (x) => String(x)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (x) => esc(x)
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, '<span class="mono">$1</span>');
  const lines = String(text).split("\n");
  let html = "", i = 0;
  const isTableRow = (l) => /^\s*\|.*\|/.test(l);
  const isTableSep = (l) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.indexOf("-") >= 0;
  while (i < lines.length) {
    const line = lines[i];
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      /* markdown 表格：| a | b | 行 + 分隔行 */
      const cells = (l) => l.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(c => c.trim());
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && isTableRow(lines[i])) { rows.push(cells(lines[i])); i++; }
      html += '<div class="tbl-wrap" style="margin:8px 0"><table class="md-table"><thead><tr>'
        + head.map(c => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>"
        + rows.map(r => "<tr>" + r.map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("")
        + "</tbody></table></div>";
      continue;
    }
    const h = line.match(/^\s*(#{1,4})\s+(.*)$/);
    if (h) {
      html += '<div class="md-h" style="font-weight:700;margin:' + (h[1].length <= 2 ? "10px 0 4px" : "8px 0 3px")
        + ';font-size:' + (h[1].length <= 2 ? "14.5px" : "13.5px") + '">' + inline(h[2]) + "</div>";
      i++; continue;
    }
    const li = line.match(/^\s*[-*•]\s+(.*)$/);
    if (li) {
      html += '<div class="md-li" style="padding-left:14px;position:relative">'
        + '<span style="position:absolute;left:2px;color:var(--cyan)">•</span>' + inline(li[1]) + "</div>";
      i++; continue;
    }
    const num = line.match(/^\s*(\d+)[.、]\s+(.*)$/);
    if (num) {
      html += '<div class="md-li" style="padding-left:18px">' + inline(num[1] + ". ") + inline(num[2]) + "</div>";
      i++; continue;
    }
    if (line.trim() === "") { html += '<div style="height:6px"></div>'; i++; continue; }
    html += '<div>' + inline(line) + "</div>";
    i++;
  }
  return html;
}

async function aiConsumeStream(stream, bubble){
  const reader = stream.getReader();
  const dec = new TextDecoder();
  let buf = "", answer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (data === "[DONE]") continue;
      let j;
      try { j = JSON.parse(data); } catch (e) { continue; }
      if (j.error) { bubble.textContent = "⚠ " + j.error; return; }
      const delta = (j.choices && j.choices[0] && j.choices[0].delta) || {};
      const piece = delta.content || "";
      if (piece) {
        answer += piece;
        bubble.textContent = answer + " ▍";
        const msgs = document.getElementById("ai-msgs");
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
      } else if (delta.reasoning && !answer) {
        /* 思考型模型：推理阶段先给出反馈，避免长时间只有光标 */
        bubble.textContent = "💭 思考中…";
      }
    }
  }
  /* 最终答案渲染 Markdown（表格/标题/列表）；纯文本保持原样 */
  if (/[|]|^\s*#|\*\*/.test(answer) || answer.indexOf("|") >= 0) {
    bubble.classList.add("md");
    bubble.innerHTML = mdToHtml(answer);
  } else {
    bubble.classList.remove("md");
    bubble.textContent = answer;
  }
}
