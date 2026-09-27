# Wave 4b 任务书：前端运维看板单页应用（以产品愿景文档为纲）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 关联章节：第十一章（首页看板原型：设备总数/正常/预警/故障统计、设备健康状态列表、
> 今日预警、设备详情：健康度/温度/振动趋势/系统判断/创建维修工单）、
> 第十章（演示剧本：每5秒模拟出数→注入异常（温度96.7/振动9.8/电流18.3）→设备变红→
> 生成"严重"预警→自动生成维修工单→维修人员处理→工单完成→设备恢复绿色）。
>
> 前置状态：feat/d-advance-baseline，看板所需 8 个后端接口全部就绪（Wave 4a 已验收），
> 四服务 CORS 已开，142 测试全绿，E2E 20 断言全过。

## 目标

交付 `web/dashboard.html`：零构建单页应用（一个 HTML 文件内嵌 CSS/JS，仅允许 CDN 引
ECharts），浏览器直接打开即可演示完整的"监测→预警→工单→恢复"闭环。这是答辩演示的脸面。

## 页面结构（严格对照愿景文档第十一章原型）

1. **登录页**（进入时）：用户名 + 密码（种子用户，密码 demo123456）→ POST D `/api/v1/auth/login`
   换 JWT 存 localStorage；展示当前用户角色（对照 D 种子：主管/维修工程师/操作员任选其一演示）。
2. **首页看板**：
   - 顶部统计排：设备总数 / 正常(RUNNING) / 预警中(有 OPEN 预警的设备) / 维修中(MAINTAINING)——
     数字实时刷新（5s 轮询）；
   - 设备健康状态列表：设备号、名称、状态色点（绿=RUNNING/黄=预警/红=MAINTAINING 或严重）、
     当前健康度（从 B 预警/评估数据取最近一次 healthScore，无则显示"--"）；
   - 今日预警栏：B `/api/v1/warnings` 最新条目（时间、设备、风险等级色标、疑似故障）。
3. **设备详情页**（点击设备卡片进入）：
   - 基本信息区（GET A 单设备）；
   - 温度/振动/电流三张趋势图（GET A telemetry，ECharts 折线，最近 30 个点）；
   - 系统判断区：最近预警的 suspectedFault / recommendedAction / healthScore；
   - **"模拟数据注入"控制台**（第十章演示剧本的核心道具）：
     a) "注入异常（严重）"按钮：温度 96.7 / 振动 9.8 / 电流 18.3（文档演示值）→
        POST A telemetry 存样本 → POST B health-evaluations 评估 → 期待 CRITICAL →
        B 后台自动 WarningRaised → C 自动建单 → 看板设备变红、预警栏出现新条目；
     b) "恢复正常数据"按钮：温度 65.2 / 振动 3.4 / 电流 11.7（文档正常值）→ 同链路，
        期待健康度回升；
     c) 注入操作有按钮级 loading 与结果提示（成功/失败原因），日志区逐条打印
        "时间 | 动作 | 请求 | 结果"（演示时可向评委展示全链路）。
4. **工单列表页**：GET C `/api/v1/work-orders` 分页表格（单号、设备、状态中文、创建时间、
   预警编号），点击行展开详情与操作按钮——按当前用户权限渲染：
   主管可 CONFIRM/ASSIGN（选择维修工程师）、工程师可 ACCEPT/START/SUBMIT_FOR_INSPECTION、
   主管 PASS_INSPECTION/REJECT_INSPECTION；每步带 X-User-Id（登录用户），
   乐观锁 expectedVersion 从详情取。工单 COMPLETED 后设备在首页变回绿色（E2E-04 已证链路）。

## 技术要求

- 单文件 `web/dashboard.html`，内嵌 CSS/JS；ECharts 用 CDN（jsdelivr）；
  其余零依赖、零构建，双击或任意静态服务器可开；
- 所有后端调用走 fetch，base 地址可配（页面顶部小输入框默认 http://127.0.0.1:8101~8104），
  服务间请求带 X-Internal-Token: dev-internal-token-change-me，用户态请求带 Authorization: Bearer JWT；
- 5s 轮询刷新统计与列表；图表增量追加不整页刷新；
- 中文界面、工业风格深色主题（参照文档"工业设备智能运维平台"标题风格）；
- 所有接口路径/字段严格按 contracts/openapi.yaml，禁止自造。

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"，
四个 FastAPI 服务（A 设备监测 8101 / B 故障预警 8102 / C 维修工单 8103 / D 身份通知 8104）
后端接口已全部就绪（CORS 已开、登录/设备列表/遥测/预警查询/工单命令等 24 个契约操作齐备）。
业务愿景见 docs/工业设备智能运维与预测性维护系统.md，先精读第十、十一章——
第十一章就是你要实现的看板原型，第十章是你要支撑的演示剧本。

你的任务：创建 web/dashboard.html（单文件零构建单页应用，仅允许 CDN 引 ECharts），
实现登录页、首页看板（统计排+设备列表+今日预警）、设备详情页（趋势图+系统判断+
模拟注入控制台）、工单列表页（状态机操作按钮）。按上方"页面结构""技术要求"执行。

关键实现提示：
- 先读这些再写：
  contracts/openapi.yaml（所有接口的请求/响应字段，特别是分页结构、
  工单命令 body：action/operatorId/expectedVersion，备件命令、健康评估
  HealthEvaluationRequest 的 evaluationId=Idempotency-Key 约定）；
  apps/integration-quality/src/infrastructure/seed.py（有哪些种子用户、角色、权限，
  决定按钮按角色怎么渲染）；
  apps/maintenance/src/domain/state_machine.py（工单状态流转与动作名，按钮启用逻辑）；
  scripts/e2e_demo.py（正确的调用顺序与报文构造，最好的参考实现）；
- 注入异常链路的正确顺序：POST A telemetry（source=SIMULATOR，带 batchId/sampleId uuid、
  Idempotency-Key）→ POST B health-evaluations（evaluationId=新 uuid=Idempotency-Key，
  sample 用刚注入那条的数据）→ 轮询 C work-orders 与 B warnings 看闭环结果（B→C 异步，
  给 2~5s）；
- 工单操作按钮按状态机当前态禁用不合法动作（PENDING_CONFIRMATION 只能 CONFIRM 等），
  操作后刷新详情与设备状态；
- 健康度显示：从 B warnings 最新评估结果取 healthScore；正常无预警设备显示 "--"。

完成后必须实际验证并贴输出：
1. powershell -File scripts/start_all.ps1（启动四服务）；
2. 用浏览器自动化或 curl 模拟看板的每个核心请求（登录→列表→注入→工单流转），
   证明页面调用的每个接口都能通（至少贴：登录、设备列表、注入异常、评估、
   自动建单、CONFIRM、PASS_INSPECTION 这 7 步的真实响应）；
3. python scripts/e2e_demo.py 重跑（确认无回归，20 断言全过）；
4. powershell -File scripts/start_all.ps1 -Stop。

约束：
- 允许改动：仅新增 web/dashboard.html（+ 可选 web/README.md 使用说明）与本任务书使用记录；
- 禁止改动：任何 src/、contracts/、scripts/、tests/ 文件；
- 页面必须对接口失败有明确错误提示（不能白屏、不能静默吞错）；
- 完成后输出：dashboard.html 全文行数与结构说明、7 步验证输出、e2e 重跑输出。
完成后在本任务书末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. 我启动服务后用无头浏览器（或最低限度 curl 逐接口模拟页面行为）验证：
   登录→设备列表→注入异常→CRITICAL→自动建单→工单流转全 COMPLETED→设备恢复绿；
2. 页面零构建可开（检查 HTML 引用：除 ECharts CDN 外无其他外部依赖）；
3. 7 步验证输出齐全，每步真实 HTTP 响应；
4. e2e_demo.py 无回归（20 断言全过）；
5. 改动范围 diff 核对：仅 web/ 新文件 + 任务书使用记录。

## 使用记录

- 2026-09-26 · 湛卢 IDE · 任务：交付 `web/dashboard.html`（774 行，单文件零构建 SPA，仅 jsdelivr CDN 引 ECharts 5.5.0）。
  - **四视图**：登录页（快捷选择主管/工程师/操作员三种子账号，JWT 存 localStorage、顶栏展示角色徽标）→ 首页看板（统计排 4 卡 5s 轮询、设备健康状态列表含状态色点与健康度、今日预警栏）→ 设备详情页（基本信息 + 温度/振动/电流三张 ECharts 趋线图各 30 点 + 系统判断区 + 模拟注入控制台与逐条操作日志）→ 工单列表页（分页表格、行展开、按钮按登录用户权限与 state_machine.py 状态机双重过滤渲染）。
  - **注入链路**（第十章剧本）：注入异常（96.7/9.8/18.3）→ POST A telemetry（source=SIMULATOR、batchId/sampleId uuid、Idempotency-Key）→ POST B health-evaluations（evaluationId=Idempotency-Key）→ CRITICAL → B 异步预警 → C 自动建单（等 2.5s 后刷新全链路可见）；恢复正常（65.2/3.4/11.7）同链路，健康度 100 回升。
  - **鉴权**：用户态请求（设备/预警/遥测/工单查询与命令）统一带 `Authorization: Bearer JWT`；注入与评估带 `X-Internal-Token`；工单命令另带 `X-User-Id`（登录用户）+ `Idempotency-Key`，`expectedVersion` 从展开行快照取。
  - **7 步真实验证**（PowerShell 直调，真实响应已核）：① login 200（JWT+user）② 设备列表 200（total=3）③ 注入 accepted=1 ④ 评估 CRITICAL/0.0 ⑤ 轮询自动建单 WO-…-8783 PENDING_CONFIRMATION ⑥ CONFIRM→PENDING_ASSIGNMENT ⑦ PASS_INSPECTION→COMPLETED v6，预警 RESOLVED、设备恢复 RUNNING。
  - **浏览器验证**（Playwright + http.server）：登录→看板渲染（统计 3/1/0/0、中文正常）→ EQ-000001 详情三图有数据→注入异常→页面日志 4 条（遥测/评估 CRITICAL/生成预警 WARN-…-0005/闭环刷新）→ 设备变红→自动建单 WO-…-3435 首行展示→主管 CONFIRM/ASSIGN、工程师登录（角色切换后按钮按权限重渲染，工程师仅见 ACCEPT）ACCEPT/START/SUBMIT_FOR_INSPECTION（表单含维修结论）、主管 PASS_INSPECTION → COMPLETED → 预警 RESOLVED、设备恢复绿、统计回到 3/1/0/0 → 恢复正常注入 LOW/健康度 100。
  - **E2E 重跑**：`python scripts/e2e_demo.py` 20 断言全过（1.83s），无回归。
  - **实现中修复的三处缺陷**：① `authHeaders()` 定义后未挂接——5 处用户态 api() 调用补 `Authorization: Bearer JWT`（任务书技术要求）；② C 列表已按 createdAt 降序而前端多余 `.reverse()` 致最新单沉底——删除反转；③ 工单操作后无条件刷新设备详情/遥测，未进过详情页时请求 `/equipment/null` 404——改为 `state.openEq` 非空才刷并在两个函数入口防御判空。
  - **改动范围**：仅新增 `web/dashboard.html` + 本使用记录；未动任何 src/、contracts/、scripts/、tests/ 文件。验证产生的临时截图与 .playwright-mcp/ 已清理。
- 2026-09-26 · 湛卢 IDE · 任务：代码审查修复（4 项，修复后 822 行）。
  - **色点严重=红**：`equipmentLight` 原以 `h.status === "CRITICAL"` 判严重，但 healthMap.status 存的是预警状态（OPEN/ACKNOWLEDGED），分支恒假——注入 CRITICAL 后设备仍黄，违背剧本"注入异常→设备变红"；改为 `h.riskLevel === "CRITICAL"`。已验证：注入 96.7/9.8/18.3 后设备 RUNNING 状态下立即红、统计"维修中"+1。
  - **轮询保留填写中的表单**：工单页 5s 轮询全量重建表格会收起展开的操作表单并丢失输入；新增 `state._openForm` 登记当前表单，`renderOrders` 重建前缓存 input/select 值、重建后校验"行仍展开且动作仍合法"再渲染并还原，提交成功才清除。已验证：ASSIGN 下拉与 SUBMIT 文本表单各跨 7s 轮询仍展开、值保留；操作失败自动还原可改后重试。
  - **图表增量追加**：落实任务书"图表增量追加不整页刷新"——`telemetrySeen` 由死字段改为按 sampleId 去重、`chartData` 滚动窗口保留最近 30 点，切换设备时重置。已验证：注入后 7→8 点追加（新点 96.7℃），旧点不重置。
  - **innerHTML XSS 转义**：新增 `esc()` 工具，设备列表/预警栏/系统判断/工单行与展开面板/操作日志所有后端字段（name、title、suspectedFault、conclusion 等）插入前统一转义。已验证：`<script>alert(1)</script>` 设备名与含 `<img onerror>` 的维修结论在 DOM 中均呈 `&lt;` 实体文本，无未转义标签注入。
  - **回归**：修复后页面内全闭环重演（注入 CRITICAL→自动建单→CONFIRM/ASSIGN/ACCEPT/START/SUBMIT/PASS_INSPECTION→COMPLETED→设备恢复绿、预警 RESOLVED）；`python scripts/e2e_demo.py` 20 断言全过（1.41s）。
