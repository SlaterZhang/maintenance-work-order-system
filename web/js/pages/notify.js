/* ============================================================================
 * 页面：通知中心（#/notify）
 *
 * 数据来源（真实接口）：
 *   D GET /api/v1/notifications  通知任务分页查询（D-API-04，登录身份即可，只读）
 *
 * 必须讲清的两个边界（都在界面上如实标注，不糊过去）：
 *   1. 投递入口 POST /api/v1/notifications 是 C-INT-07，要求 X-Internal-Token，
 *      是服务间接口（openapi.yaml 的 x-caller-members: [A, B, C]）。浏览器只持有
 *      用户 JWT，不持有也不该持有内部令牌，所以本页不提供"发通知"按钮。
 *   2. 当前服务端还没有任何事件生产者调用 C-INT-07：
 *        - B 的 outbox 已定义 WarningNotification 类型并在 event_dispatch.py:94
 *          实现 _deliver_notification，但全仓没有任何地方 enqueue 它；
 *        - C 的 MemberDClient.submit_notification 已实现，但没有调用点。
 *      所以发送记录现在是空的——这是后端尚未接通的一环，不是界面缺陷。
 * ==========================================================================*/

// 契约 templateCode 枚举的 5 项（contracts/openapi.yaml 的 NotificationRequest）
const NOTIFY_TEMPLATES = [
  { code:"WARNING_CREATED",           zh:"预警创建",     by:"B",
    flow:"B 评估判定 HIGH/CRITICAL 建预警后", to:"预警分析师、维修主管",
    variables:"equipmentId, warningId, riskLevel, healthScore" },
  { code:"WORK_ORDER_CREATED",        zh:"工单创建",     by:"C",
    flow:"C 建单成功后", to:"维修主管",
    variables:"orderId, equipmentId, priority" },
  { code:"WORK_ORDER_ASSIGNED",       zh:"工单派发",     by:"C",
    flow:"ASSIGN 派单成功后", to:"维修工程师（受派人）",
    variables:"orderId, assigneeId, dueAt" },
  { code:"WORK_ORDER_STATUS_CHANGED", zh:"工单状态变更", by:"C",
    flow:"命令推进状态后", to:"创建人、负责人",
    variables:"orderId, fromStatus, toStatus" },
  { code:"SPARE_REQUEST_PENDING",     zh:"备件申请待审", by:"C",
    flow:"备件申请创建后", to:"维修主管、仓库管理员",
    variables:"requestId, orderId, sparePartId" },
];
const NOTIFY_ZH = {};
NOTIFY_TEMPLATES.forEach(t => { NOTIFY_ZH[t.code] = t.zh; });

// 已实现但尚未被业务触达的调用点（如实列出，便于后续接通）
const NOTIFY_WIRING = [
  { side:"B", state:"已实现投递",
    where:"apps/fault-warning/src/application/event_dispatch.py:94",
    detail:"_deliver_notification(row, body) → member_d.submit_notification" },
  { side:"B", state:"已定义类型",
    where:"apps/fault-warning/src/domain/enums.py:81",
    detail:"OutboxEventType.WARNING_NOTIFICATION = \"WarningNotification\"" },
  { side:"B", state:"未接通",
    where:"（无调用点）",
    detail:"全仓搜不到 enqueue(WARNING_NOTIFICATION)，预警建单后不发通知" },
  { side:"C", state:"已实现客户端",
    where:"apps/maintenance/src/interfaces/clients/member_d.py:59",
    detail:"MemberDClient.submit_notification(recipients, template_code, …)" },
  { side:"C", state:"未接通",
    where:"（无调用点）",
    detail:"work_order_service.py / spare_service.py 均未调用它" },
  { side:"D", state:"已实现入口",
    where:"apps/integration-quality/src/interfaces/http/notifications.py:47",
    detail:"POST /notifications（C-INT-07，internal_token，带 Idempotency-Key）" },
];

function notifyBody(){
  const list = state.notifications || [];
  const today = new Date().toISOString().slice(0, 10);
  const todayN = list.filter(n => String(n.createdAt || "").slice(0, 10) === today).length;
  const unwired = NOTIFY_WIRING.filter(w => w.state === "未接通").length;

  let html = pageHdr("通知中心", "模板目录 · 发送记录 · 渠道与重试", "");

  html += noticeLive("数据来源：真实接口 — D <span class=\"mono\">GET /api/v1/notifications</span>"
    + "（D-API-04，登录身份即可，已实读，当前 " + list.length + " 条）。模板目录取自契约 "
    + "<span class=\"mono\">NotificationRequest.templateCode</span> 的 5 项枚举。");

  html += noticeWarn("<b>发送记录为空，原因在服务端而不在界面：</b>投递入口 "
    + "<span class=\"mono\">POST /api/v1/notifications</span>（C-INT-07）是<b>服务间</b>接口，要求 "
    + "<span class=\"mono\">X-Internal-Token</span>（<span class=\"mono\">openapi.yaml</span> 声明 "
    + "<span class=\"mono\">x-caller-members: [MEMBER_A, MEMBER_B, MEMBER_C]</span>）；"
    + "而目前<b>没有任何一侧真的调用它</b>——B 实现了投递函数但无 enqueue 调用点，"
    + "C 实现了 HTTP 客户端但无调用点，A 侧连客户端都还没有。"
    + "所以本页不提供「发送」按钮：浏览器不持有也不该持有内部令牌。");

  html += '<div class="grid g4 mt">'
    + kpi("cyan",   "今日发送", todayN, "按 createdAt 统计")
    + kpi("purple", "发送总数", list.length, "全部历史")
    + kpi("dim",    "通知模板", NOTIFY_TEMPLATES.length, "契约枚举 5 项")
    + kpi(unwired ? "yellow" : "green", "未接通调用点", unwired, "服务端待补")
    + '</div>';

  // 发送记录（真实数据，当前为空）
  html += '<div class="card mt">' + sect("发送记录", list.length + " 条")
    + table(["时间", "通知编号", "模板", "通道", "接收人", "业务引用", "traceId"],
        list.map(n => [
          '<span class="mini">' + fmtTime(n.createdAt) + '</span>',
          '<span class="mono">' + h(n.notificationId || "—") + '</span>',
          h(NOTIFY_ZH[n.templateCode] || n.templateCode || "—"),
          n.channel ? tag("notificationChannel", n.channel) : "—",
          (n.recipientUserIds || []).map(r => '<span class="mono mini">' + h(r) + '</span>').join("、") || "—",
          n.businessReference ? '<span class="mono mini">' + h(n.businessReference) + '</span>' : "—",
          '<span class="mono mini">' + h(n.traceId || "—") + '</span>',
        ]),
        { emptyText: "暂无发送记录",
          emptyHint: "D 服务的 notification_task 表当前 0 行——因为还没有服务调用 C-INT-07 投递接口" })
    + '</div>';

  // 模板目录
  html += '<div class="card mt">' + sect("通知模板目录", "契约枚举 5 项")
    + table(["模板码", "名称", "触发方", "触发时机", "默认接收角色", "variables 建议字段"],
        NOTIFY_TEMPLATES.map(t => [
          '<span class="mono mini">' + h(t.code) + '</span>',
          h(t.zh),
          '<span class="pill b-purple">' + h(t.by) + '</span>',
          '<span class="mini">' + h(t.flow) + '</span>',
          '<span class="mini">' + h(t.to) + '</span>',
          '<span class="mono mini">' + h(t.variables) + '</span>',
        ]))
    + '</div>';

  // 接通清单 —— 把"缺哪一步"写明白，比假装功能完整强
  html += '<div class="grid g-2-1 mt">'
    + '<div class="card">' + sect("接通清单", "哪些已就绪、哪些还缺")
    + table(["侧", "状态", "位置", "说明"], NOTIFY_WIRING.map(w => [
          '<span class="pill b-' + (w.state === "未接通" ? "red"
            : w.state.startsWith("已") ? "green" : "dim") + '">' + h(w.side) + '</span>',
          w.state === "未接通"
            ? '<span class="pill b-red">' + h(w.state) + '</span>'
            : '<span class="pill b-green">' + h(w.state) + '</span>',
          '<span class="mono mini">' + h(w.where) + '</span>',
          '<span class="mini">' + h(w.detail) + '</span>',
        ]))
    + '<div class="mini mt" style="line-height:1.8">'
    + '接通需要补的是<b>事件生产者</b>：B 在 '
    + '<span class="mono">evaluation_service._enqueue_warning_raised()</span> 里追加一条 '
    + '<span class="mono">WARNING_NOTIFICATION</span> outbox 事件；C 在 '
    + '<span class="mono">work_order_service.execute_command()</span> 的成功分支里调用 '
    + '<span class="mono">MemberDClient.submit_notification()</span>。两者都是既有代码的扩展，'
    + '不需要新接口。</div>'
    + '</div>'

    + '<div class="card">' + sect("渠道与重试策略", "契约与实现")
    + table(["渠道", "用途", "实现状态"], [
        ['<span class="mono">IN_APP</span>', "站内信：写入通知任务表，前端铃铛角标提示",
         '<span class="pill b-green">契约已定义</span>'],
        ['<span class="mono">EMAIL</span>', "邮件：日报与库存告警等非实时场景",
         '<span class="pill b-green">契约已定义</span>'],
      ])
    + '<div class="timeline mt">'
    + '<div class="tl ok"><div class="tt">投递不阻断主链路</div><div class="td">'
      + 'C-INT-07 返回 <code>202 Accepted</code> 并支持 <code>Idempotency-Key</code>——'
      + '通知是旁路，业务事务不等它。B 侧走 outbox 模式：先写本地事件表，'
      + '再由 <code>dispatch_pending()</code> 异步投递，投递失败只标 FAILED，不回滚业务。</div></div>'
    + '<div class="tl ok"><div class="tt">幂等靠业务键</div><div class="td">'
      + 'B 用 <code>row.event_id</code> 作为幂等键，重投不会产生重复通知。'
      + '这是 outbox 模式的关键：至少一次投递 + 幂等消费 = 恰好一次的效果。</div></div>'
    + '<div class="tl warn"><div class="tt">为什么不做重试队列</div><div class="td">'
      + 'outbox 表本身就是重试队列（<code>status=PENDING/FAILED</code> 可重投）。'
      + '再叠一层消息中间件对演示系统是过度设计，也偏离"四服务边界清晰"这一立项前提。</div></div>'
    + '</div></div></div>';

  return html;
}

registerPage("notify", {
  async load(ctx){
    state.notifications = await loadNotifications();
    return notifyBody();
  },
});
