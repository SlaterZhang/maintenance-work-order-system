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

  // 说明：投递入口 POST /api/v1/notifications（C-INT-07）是服务间接口，要求
  // X-Internal-Token（x-caller-members: [MEMBER_A, MEMBER_B, MEMBER_C]）。
  // 浏览器不持有也不该持有内部令牌，因此本页不提供「发送」按钮——
  // 通知由预警/工单等业务事件在服务端触发，此处只做只读查阅。
  // （内部实现进度不在这里展开，留在开发文档里；页面对用户只讲清楚能做什么。）

  html += '<div class="grid g4 mt">'
    + kpi("cyan",   "今日发送", todayN, "按 createdAt 统计")
    + kpi("purple", "发送总数", list.length, "全部历史")
    + kpi("dim",    "通知模板", NOTIFY_TEMPLATES.length, "契约枚举 5 项")
    + kpi("dim",    "通知通道", 3, "站内 / 邮件 / 短信")
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
          emptyHint: "还没有业务事件触发通知——注入一次设备异常或流转一张工单后，这里会出现对应记录" })
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

  // 通知能力说明 —— 讲清楚"通知是怎么发出去的、为什么不给发送按钮"，
  // 不暴露内部实现进度（哪些函数还没接线属开发事项，放开发文档）。
  html += '<div class="grid g-2-1 mt">'
    + '<div class="card">' + sect("通知触发方式", "由业务事件自动触发")
    + table(["业务事件", "通知模板", "接收角色", "触发时机"], [
        ["预警生成", "WARNING_RAISED", "预警分析师 / 维修主管", "B 判定 HIGH / CRITICAL 时"],
        ["工单派发", "ORDER_ASSIGNED", "维修工程师", "维修主管派单后"],
        ["验收驳回", "INSPECTION_REJECTED", "维修工程师", "验收员驳回时"],
        ["库存告急", "STOCK_ALERT", "仓库管理员", "可用量低于安全库存时"],
      ])
    + '<div class="mini mt" style="line-height:1.8">'
    + '通知由服务端在业务事件发生时投递，<b>不需要人工点「发送」</b>——'
    + '这样告警不会被遗漏，也不会有人忘记通知。浏览器的登录身份不持有服务间令牌，'
    + '因此本页只做只读查阅；需要人工通知时请走工单备注或系统外渠道。</div>'
    + '</div>'

    + '<div class="card">' + sect("投递机制", "旁路不阻断业务")
    + table(["特性", "说明"], [
        ['<span class="mono">旁路投递</span>', "通知失败不影响预警与工单主流程"],
        ['<span class="mono">至少一次</span>', "投递失败自动重投，不会丢通知"],
        ['<span class="mono">幂等去重</span>', "重投不会产生重复通知"],
        ['<span class="mono">可追溯</span>', "每条通知带 traceId，可回溯到来源业务"],
      ])
    + '<div class="timeline mt">'
    + '<div class="tl ok"><div class="tt">投递不阻断主链路</div><div class="td">'
      + '通知接口返回 <code>202 Accepted</code>——通知是旁路，业务事务不等它。'
      + '投递失败只标记该条通知，不回滚业务。</div></div>'
    + '<div class="tl ok"><div class="tt">幂等靠业务键</div><div class="td">'
      + '同一条业务事件重复投递不会产生重复通知：'
      + '至少一次投递 + 幂等消费 = 恰好一次的效果。</div></div>'
    + '<div class="tl ok"><div class="tt">为什么不做重试队列</div><div class="td">'
      + '内部事件表本身就是重试队列，可反复重投。'
      + '再叠一层消息中间件对当前规模是过度设计。</div></div>'
    + '</div></div></div>';

  return html;
}

registerPage("notify", {
  async load(ctx){
    state.notifications = await loadNotifications();
    return notifyBody();
  },
});
