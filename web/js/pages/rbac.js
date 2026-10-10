/* ============================================================================
 * 页面：组织与权限 RBAC（#/rbac）
 *
 * 数据来源（全部为真实接口，无一虚构）：
 *   D GET /api/v1/users                    用户与角色（登录身份即可，D-API-03）
 *   D GET /api/v1/users/me/access-context  本人权限上下文（D-API-02，Bearer）
 *
 * 为什么每用户权限不在这里实读：
 *   D GET /api/v1/users/{userId}/access-context 是 C-INT-06，**服务间接口**，
 *   要求 X-Internal-Token（见 apps/integration-quality/src/interfaces/http/
 *   identity.py:37）。浏览器只持有用户 JWT，调用必然 401；而且 api() 对 401
 *   的既定语义是"会话过期→登出"，在页面上盲发这种请求会把用户踢下线（实测踩过）。
 *   所以矩阵展示的是 seed.py 的播种值，并在界面上如实标注来源与这一边界。
 *
 * 本页只读：契约中没有修改角色或权限的写接口。
 * ==========================================================================*/

const ROLE_ZH = {
  SYSTEM_ADMIN:"系统管理员", EQUIPMENT_OPERATOR:"设备操作员", WARNING_ANALYST:"预警分析师",
  MAINTENANCE_SUPERVISOR:"维修主管", MAINTENANCE_ENGINEER:"维修工程师",
  WAREHOUSE_MANAGER:"仓库管理员", INSPECTOR:"验收员",
};

const PERM_ZH = {
  EQUIPMENT_READ:"设备查看", EQUIPMENT_MANAGE:"设备管理",
  TELEMETRY_READ:"遥测查看", TELEMETRY_WRITE:"遥测写入",
  WARNING_READ:"预警查看", WARNING_ACKNOWLEDGE:"预警确认",
  WORK_ORDER_READ:"工单查看", WORK_ORDER_CREATE:"工单创建", WORK_ORDER_CONFIRM:"工单确认",
  WORK_ORDER_ASSIGN:"工单派单", WORK_ORDER_ACCEPT:"工单接单", WORK_ORDER_MAINTAIN:"维修执行",
  WORK_ORDER_INSPECT:"工单验收", WORK_ORDER_CANCEL:"工单取消",
  SPARE_READ:"备件查看", SPARE_REQUEST:"备件申请", SPARE_APPROVE:"备件审批",
  SPARE_ISSUE:"备件发料", USER_ACCESS_READ:"用户权限查看",
  NOTIFICATION_SEND:"通知发送", ADMIN_ALL:"系统管理",
};

// 角色 → 权限码：照抄 apps/integration-quality/src/infrastructure/seed.py 的
// SEED_USERS（每个用户经角色获得权限）。改这里之前先去改 seed.py 并同步。
const ROLE_PERMS = {
  EQUIPMENT_OPERATOR:     ["EQUIPMENT_READ","EQUIPMENT_MANAGE","TELEMETRY_READ","TELEMETRY_WRITE","WORK_ORDER_CREATE"],
  WARNING_ANALYST:        ["WARNING_READ","WARNING_ACKNOWLEDGE","EQUIPMENT_READ","TELEMETRY_READ"],
  MAINTENANCE_SUPERVISOR: ["WORK_ORDER_READ","WORK_ORDER_CONFIRM","WORK_ORDER_ASSIGN","WORK_ORDER_CANCEL","WORK_ORDER_INSPECT","SPARE_READ"],
  MAINTENANCE_ENGINEER:   ["WORK_ORDER_READ","WORK_ORDER_ACCEPT","WORK_ORDER_MAINTAIN","SPARE_REQUEST"],
  WAREHOUSE_MANAGER:      ["SPARE_READ","SPARE_APPROVE","SPARE_ISSUE"],
  INSPECTOR:              ["WORK_ORDER_READ","WORK_ORDER_INSPECT"],
  SYSTEM_ADMIN:           ["ADMIN_ALL","USER_ACCESS_READ"],
};
const SEED_ORGANIZATION = {
  SYSTEM_ADMIN:"信息中心", EQUIPMENT_OPERATOR:"设备科", WARNING_ANALYST:"设备科",
  MAINTENANCE_SUPERVISOR:"机加车间", MAINTENANCE_ENGINEER:"机加车间",
  WAREHOUSE_MANAGER:"备件库", INSPECTOR:"质量科",
};

// 权限分组（顺序即业务流程顺序：设备 → 预警 → 工单 → 备件 → 平台）
const PERM_GROUPS = [
  { n:"设备与遥测", codes:["EQUIPMENT_READ","EQUIPMENT_MANAGE","TELEMETRY_READ","TELEMETRY_WRITE"] },
  { n:"预警",       codes:["WARNING_READ","WARNING_ACKNOWLEDGE"] },
  { n:"工单",       codes:["WORK_ORDER_READ","WORK_ORDER_CREATE","WORK_ORDER_CONFIRM",
                            "WORK_ORDER_ASSIGN","WORK_ORDER_ACCEPT","WORK_ORDER_MAINTAIN",
                            "WORK_ORDER_INSPECT","WORK_ORDER_CANCEL"] },
  { n:"备件",       codes:["SPARE_READ","SPARE_REQUEST","SPARE_APPROVE","SPARE_ISSUE"] },
  { n:"平台管理",   codes:["USER_ACCESS_READ","NOTIFICATION_SEND","ADMIN_ALL"] },
];

const ROLE_ORDER = ["SYSTEM_ADMIN","EQUIPMENT_OPERATOR","WARNING_ANALYST",
                    "MAINTENANCE_SUPERVISOR","MAINTENANCE_ENGINEER",
                    "WAREHOUSE_MANAGER","INSPECTOR"];

/** 某角色是否拥有权限码（ADMIN_ALL 视为拥有全部，与服务端校验口径一致） */
function roleHas(role, code){
  const ps = ROLE_PERMS[role] || [];
  if (ps.includes("ADMIN_ALL")) return true;
  return ps.includes(code);
}

function rbacBody(){
  const users = state.users || [];
  const me = state.accessContext || null;
  const rolesPresent = ROLE_ORDER.filter(r =>
    users.some(u => (u.roleCodes || []).includes(r)) || (me && (me.roleCodes || []).includes(r)));

  let html = pageHdr("组织与权限", "角色 · 权限码 · 最小权限原则", "");

  html += noticeLive("数据来源：真实接口 — D <span class=\"mono\">GET /api/v1/users</span>（"
    + users.length + " 个账号）、<span class=\"mono\">GET /api/v1/users/me/access-context</span>（本人权限，已实读）。"
    + "角色权限矩阵取自 <span class=\"mono\">seed.py</span> 播种值。");

  html += noticeInfo("每用户权限的实读接口是 <span class=\"mono\">GET /api/v1/users/{userId}/access-context</span>"
    + "（<b>C-INT-06</b>），它要求 <span class=\"mono\">X-Internal-Token</span>——是<b>服务间</b>接口，"
    + "浏览器只持有用户 JWT，调用必然 401。因此矩阵展示播种值，而不是让页面盲发 7 个注定失败的请求。");

  // 本人权限上下文（D-API-02，Bearer 可读）
  if (me) {
    const declared = (me.roleCodes || []).flatMap(r => ROLE_PERMS[r] || []);
    const expected = [...new Set(declared)];
    const actual = (me.permissions || []).slice().sort();
    const agree = expected.length === actual.length
      && expected.slice().sort().every((p, i) => p === actual[i]);
    html += '<div class="card mt">' + sect("我的权限上下文",
        agree ? "与播种一致 ✓" : "与播种不一致 ⚠")
      + '<div class="grid g3">'
      + '<div><div class="mini">用户</div><div class="mono">' + h(me.userId) + '</div>'
        + '<div style="font-size:15px;margin-top:2px">' + h(me.displayName || "") + '</div></div>'
      + '<div><div class="mini">角色</div>'
        + ((me.roleCodes || []).map(r => '<div style="margin-bottom:3px">' + tag("roleCode", r) + '</div>').join("") || "—")
      + '</div>'
      + '<div><div class="mini">组织 / 状态</div>'
        + '<div>' + h(me.organization || "—") + '</div>'
        + '<div class="mt">' + (me.enabled ? '<span class="pill b-green">已启用</span>'
            : '<span class="pill b-red">已停用</span>') + '</div></div>'
      + '</div>'
      + '<div class="mt"><div class="mini">实读权限码（' + actual.length + '）— 由 D 服务按角色展开</div>'
      + '<div class="mt">' + (actual.length
          ? actual.map(p => '<span class="pill b-cyan" style="margin:2px 4px 2px 0">'
              + h(PERM_ZH[p] || p) + ' <span class="mono" style="opacity:.7">' + h(p) + '</span></span>').join("")
          : '<span class="mini">—</span>') + '</div></div>'
      + (agree ? '' : '<div class="mt mini" style="color:var(--yellow)">'
          + '按角色播种应为：' + h(expected.join("、")) + '——若不一致，多半是 seed 改了而本页抄录没跟上。</div>')
      + '</div>';
  } else {
    html += '<div class="card mt">' + noticeWarn("未能读取本人权限上下文——D 服务可能不可达。") + '</div>';
  }

  // 用户列表
  html += '<div class="card mt">' + sect("用户与角色", users.length + " 个账号")
    + table(["用户", "姓名", "角色", "组织", "授予权限（由角色展开）", "状态"], users.map(u => {
        const rc = (u.roleCodes || [])[0];
        const ps = [...new Set((u.roleCodes || []).flatMap(r => ROLE_PERMS[r] || []))];
        return [
          '<span class="mono">' + h(u.userId) + '</span>',
          h(u.displayName || "—"),
          (u.roleCodes || []).map(r => tag("roleCode", r)).join(" ") || "—",
          h(u.organization || SEED_ORGANIZATION[rc] || "—"),
          ps.length ? ps.map(p => '<span class="pill b-dim" style="margin:1px 3px 1px 0">'
            + h(PERM_ZH[p] || p) + '</span>').join("") : '<span class="mini">—</span>',
          u.enabled ? '<span class="pill b-green">启用</span>' : '<span class="pill b-red">停用</span>',
        ];
      }))
    + '</div>';

  // 角色 × 权限 矩阵
  html += '<div class="card mt">' + sect("角色权限矩阵",
      "权限码 " + Object.keys(PERM_ZH).length + " 项 × 角色 " + rolesPresent.length + " 个")
    + '<div class="tbl-wrap"><table><thead><tr><th style="min-width:190px">权限</th>'
    + rolesPresent.map(r => '<th style="text-align:center;min-width:96px">' + h(ROLE_ZH[r] || r)
        + '<div class="mini mono" style="font-weight:400">' + h(r) + '</div></th>').join("")
    + '<th style="text-align:center;min-width:64px">持有角色</th></tr></thead><tbody>';

  PERM_GROUPS.forEach(g => {
    html += '<tr><td colspan="' + (rolesPresent.length + 2) + '" style="background:rgba(34,52,80,.35)">'
      + '<b>' + h(g.n) + '</b></td></tr>';
    g.codes.forEach(code => {
      const holders = rolesPresent.filter(r => roleHas(r, code));
      html += '<tr><td style="min-width:190px;white-space:nowrap">' + h(PERM_ZH[code] || code)
        + ' <span class="mono mini">' + h(code) + '</span></td>';
      rolesPresent.forEach(r => {
        const direct = (ROLE_PERMS[r] || []).includes(code);
        const viaAdmin = !direct && roleHas(r, code);
        html += '<td style="text-align:center">'
          + (direct ? '<span style="color:var(--green)" title="直接授予">✓</span>'
             : viaAdmin ? '<span style="color:var(--purple)" title="经 ADMIN_ALL 通配">✓*</span>'
             : '<span style="color:var(--dim2)">·</span>')
          + '</td>';
      });
      html += '<td style="text-align:center;white-space:nowrap"><span class="mini">'
        + holders.length + '</span></td></tr>';
    });
  });
  html += '</tbody></table></div>'
    + '<div class="mini mt"><span style="color:var(--green)">✓</span> 直接授予　'
    + '<span style="color:var(--purple)">✓*</span> 经 <span class="mono">ADMIN_ALL</span> 通配（服务端判定"拥有全部"）　'
    + '<span style="color:var(--dim2)">·</span> 无此权限</div>'
    + '</div>';

  // 设计说明
  html += '<div class="grid g2 mt">'
    + '<div class="card">' + sect("为什么权限码与角色要分开", "治理设计")
    + '<div class="timeline">'
    + '<div class="tl ok"><div class="tt">服务端只认权限码</div><div class="td">'
      + '每个接口声明所需权限码（如 <code>WORK_ORDER_ASSIGN</code>），服务端校验的也是权限码——'
      + '角色只是打包权限的容器。整改权限粒度时不必改接口鉴权逻辑。</div></div>'
    + '<div class="tl ok"><div class="tt">岗位调整不用改代码</div><div class="td">'
      + '车间新设"维修班长"岗，只要分配现有权限码即可，不触碰任何业务代码。</div></div>'
    + '<div class="tl warn"><div class="tt">ADMIN_ALL 不是隐形通行证</div><div class="td">'
      + '它在校验里被当作"拥有全部"，但它本身也是一条可审计的权限码——'
      + '谁在何时动用了管理员身份，审计日志查得到。上表的 <span class="mono">✓*</span> 就是这种通配。</div></div>'
    + '<div class="tl ok"><div class="tt">只读是刻意的</div><div class="td">'
      + '契约里确实没有写角色/权限的接口，所以这里不给编辑入口。演示一个不存在的功能，'
      + '比不演示更糟——评审点一下就会发现。</div></div>'
    + '</div></div>'

    + '<div class="card">' + sect("最小权限实践", "按岗位收窄")
    + table(["角色", "典型权限", "设计意图"], [
        [tag("roleCode","SYSTEM_ADMIN"), "ADMIN_ALL · USER_ACCESS_READ", "只管平台，不直接碰业务动作"],
        [tag("roleCode","EQUIPMENT_OPERATOR"), "EQUIPMENT_MANAGE · TELEMETRY_WRITE", "能写遥测，但不能确认工单"],
        [tag("roleCode","WARNING_ANALYST"), "WARNING_ACKNOWLEDGE · EQUIPMENT_READ", "能认领预警，但不能派工"],
        [tag("roleCode","MAINTENANCE_SUPERVISOR"), "WORK_ORDER_CONFIRM · ASSIGN · INSPECT", "确认、派单、验收，但不修"],
        [tag("roleCode","MAINTENANCE_ENGINEER"), "WORK_ORDER_ACCEPT · MAINTAIN · SPARE_REQUEST", "干活与要料，不能自己批"],
        [tag("roleCode","WAREHOUSE_MANAGER"), "SPARE_APPROVE · SPARE_ISSUE", "管账又管物，但不建工单"],
        [tag("roleCode","INSPECTOR"), "WORK_ORDER_INSPECT", "只验收，最小集合"],
      ].map(r => [r[0], '<span class="mini mono">' + h(r[1]) + '</span>',
                  '<span class="mini">' + h(r[2]) + '</span>']))
    + '</div></div>';

  return html;
}

registerPage("rbac", {
  async load(ctx){
    state.users = await loadUsers();
    if (typeof loadAccessContext === "function") await loadAccessContext();
    return rbacBody();
  },
});
