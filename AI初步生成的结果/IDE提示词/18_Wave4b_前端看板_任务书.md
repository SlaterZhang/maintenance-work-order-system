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
