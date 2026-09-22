# Wave 0 契约审计报告

- 生成日期：2026-09-22
- 生成方式：湛卢 IDE（提示词 A/B/C，见 `02_Wave0_契约吸收_IDE提示词.md`）
- 对比基准：`main @ 0db10fa`（契约 v1.1.0） vs `origin/docs/api-contract-v2 @ a228a77`（契约 2.0.0）
- 差异规模：`contracts/` 下 11 个文件，+2371 / -336 行；`scripts/check_repo.py` +127 行
- 校验环境：Python 3.12.9，jsonschema 4.23.0（Draft 2020-12 + FormatChecker），PyYAML 6.0.2
- 校验方法：`git diff main origin/docs/api-contract-v2 -- contracts/` 逐文件比对；对 v1 基线与 v2 分支分别做三层枚举比对与示例报文 jsonschema 校验；交叉校验（v1 报文对 v2 schema、v2 报文对 v1 schema）；`check_repo.py --strict` 在 main / v2 两套基线实际运行

---

## A. 契约差异审计（main vs origin/docs/api-contract-v2）

### A.1 按文件分组的变更清单

#### 1. contracts/openapi.yaml（重写，约 650 行 → 2252 行）

| 变更 | v1.1.0 | v2.0.0 |
| --- | --- | --- |
| info.version | 1.1.0 | 2.0.0（升主版本） |
| 路径规模 | 6 个跨模块路径 / 6 个操作（C-INT-01~05） | 20 个路径 / 24 个操作（C-INT-01~07 + A-API/B-API/C-API/D-API） |
| 事件接收路径改名 | `/api/v1/warnings`、`/api/v1/equipment-status-events`、`/api/v1/maintenance-conclusions` | `/api/v1/integration/warning-events`（L469）、`/api/v1/integration/equipment-status-events`（L256）、`/api/v1/integration/maintenance-conclusions`（L435） |
| 预警建单响应码 | 202/400/409/500 | 202/400/401/403/404/409/422/500；422 = LOW/MEDIUM 不满足自动建单（语义变化） |
| 认证 | 无 security 定义 | 全局 `bearerAuth`（JWT）+ 服务间 `internalToken`（X-Internal-Token，L901-911） |
| 新增面向前端接口 | — | 设备 CRUD/遥测（A-API-01~05）、预警查询/确认（B-API-01~03）、工单/备件 7 个（C-API-01~07）、登录与用户（D-API-01~02）、健康评估（C-INT-02） |
| 设备查询响应 | `EquipmentSnapshot`：`type`、`productionLine`、6 个 required | `Equipment`：`equipmentType`、`productionLineId`（字段改名），required 扩至 10 个（新增 enabled/location/createdAt/updatedAt，L1153-1216） |
| 事件包络 | `schemaVersion: ^1\.[0-9]+$`、`traceId minLength 1` | `schemaVersion: ^2\.[0-9]+$`（L1925）、`traceId minLength 8`（L1934）；服务间 TraceIdHeader 提为必填 |
| WarningRaisedPayload | required 6 字段（healthScore 可选 nullable） | required 9 字段：新增必填 `healthScore`、`recommendedAction`、`metricSnapshot`（L1953-1962） |
| MaintenanceConclusionPayload | required 8 字段 | required 9 字段：新增必填 `submittedBy`；新增可选 `downtimeMinutes`（L2037-2075） |
| NotificationChannel | `IN_APP, EMAIL, SMS` | `IN_APP, EMAIL`（**删除 SMS**，L1115-1117） |
| NotificationRequest.templateCode | 自由字符串（示例 WORK_ORDER_ASSIGNED） | 收窄为 5 值枚举（L2185-2192） |
| UserAccessContext | roleCodes/permissions 为自由字符串数组 | 收窄为 RoleCode/PermissionCode 枚举引用（L2155-2166） |
| ErrorResponse | required [code,message,traceId]，details 为自由 object | required 新增 timestamp、details 改为 FieldViolation 数组，traceId minLength 8、code 加 pattern（L2230-2252） |
| 标识格式 | 字符串 + 长度限制（≤32） | 严格 pattern：`EQ-[0-9]{6}`、`WARN-[0-9]{8}-[0-9]{4}`、`WO-[0-9]{8}-[0-9]{4}`、`USER-[A-Z0-9-]{1,27}`（L1033-1056） |
| servers | 各操作单独声明 localhost:8101~8104 | 统一网关 http://localhost:8080（成员 D 维护路由） |

#### 2. contracts/shared-enums.json（+90 行）

- `contractVersion`：`1.1.0` → `2.0.0`（升主版本）
- 新增 10 组枚举：`workOrderAction`(10值)、`workOrderPriority`(P1~P4)、`workOrderSource`(3值)、`warningStatus`(5值)、`spareRequestStatus`(8值)、`spareRequestAction`(7值)、`maintenanceResult`(3值)、`notificationChannel`(2值)、`roleCode`(7值)、`permissionCode`(21值)
- `equipmentStatus`、`workOrderStatus`、`riskLevel`、`eventType`、`sourceMember` 未变

#### 3. contracts/schemas/event-envelope.schema.json

- `schemaVersion` pattern：`^1\.[0-9]+$` → `^2\.[0-9]+$`
- `traceId`：`minLength 1` → `minLength 8`

#### 4. contracts/schemas/warning-raised.payload.schema.json

- required 新增：`healthScore`（原可选）、`recommendedAction`、`metricSnapshot`（含 6 个必填子字段的对象，值域与 TelemetrySample 一致）
- `warningId`/`equipmentId`：长度约束改为严格 pattern

#### 5. contracts/schemas/maintenance-conclusion.payload.schema.json

- required 新增：`submittedBy`
- 新增可选字段：`downtimeMinutes`（integer|null, ≥0）
- `orderId`/`equipmentId`/`warningId`：长度约束改为严格 pattern

#### 6. contracts/schemas/equipment-status-changed.payload.schema.json

- `orderId`/`equipmentId`/`operatorId`：长度约束改为严格 pattern（仅约束收紧，字段集合未变）

#### 7. contracts/examples/*.json

- 三个示例 `schemaVersion`：`1.0` → `2.0`
- `warning-raised.json`：新增 `recommendedAction`、`metricSnapshot`；`modelVersion` 示例值 `health-model-1.3.0` → `rule-engine-1.0.0`
- `maintenance-conclusion.json`：新增 `submittedBy`、`downtimeMinutes`

#### 8. contracts/http/local-api.http（新增 276 行）

- VS Code REST Client 联调请求集合，覆盖 24 个操作中的主要调用链（登录、设备、遥测、预警确认、工单命令、备件命令、三个跨模块事件）
- 注意：请求 URL 全部使用 **v2 路径**（`/api/v1/integration/*` 等）并要求 Bearer JWT / X-Internal-Token，绑定 v2 契约形态

#### 9. contracts/README.md

- 「五项逻辑接口」→「七项跨模块逻辑接口」；C-INT 编号整体重排（原 C-INT-02~05 → 新 C-INT-03~05 + 新增 C-INT-02 健康评估、C-INT-06/07 身份与通知拆分）
- 引用 `http/local-api.http` 与 `docs/06_详细接口约定与联调手册.md`

### A.2 兼容性标注

| # | 变更项 | 兼容性 | 说明 |
| --- | --- | --- | --- |
| 1 | contractVersion 1.1.0 → 2.0.0 | **破坏性** | 主版本升级，声明语义不兼容 |
| 2 | 事件 schemaVersion pattern ^1 → ^2 | **破坏性** | v1 报文全部被 v2 包络校验拒绝 |
| 3 | traceId minLength 1 → 8 | **破坏性** | v1 允许 1 字符 traceId，v2 拒绝 |
| 4 | WarningRaised required +3（healthScore/recommendedAction/metricSnapshot） | **破坏性** | v1 发送方缺失字段即被拒 |
| 5 | MaintenanceConclusion required +submittedBy | **破坏性** | 同上 |
| 6 | 三个事件接收路径改名（/integration/ 前缀） | **破坏性** | v1 调用方 404 |
| 7 | NotificationChannel 删除 SMS | **破坏性** | 枚举删值 |
| 8 | EquipmentSnapshot → Equipment 字段改名（type→equipmentType、productionLine→productionLineId）+ required 扩充 | **破坏性** | 消费方字段读取失效 |
| 9 | ErrorResponse required +timestamp、details 类型改为数组 | **破坏性** | 响应解析方需改代码 |
| 10 | roleCodes/permissions/templateCode 收窄为枚举 | **破坏性** | 现有取值可能非法（如 SMS、自由模板码） |
| 11 | 全局认证要求（JWT + X-Internal-Token） | **破坏性** | v1 调用方不带凭证将 401 |
| 12 | 标识 pattern 化（EQ/WARN/WO/USER） | **破坏性**（条件性） | 已按示例格式的数据不受影响；任意 ≤32 字符的旧数据被拒 |
| 13 | warnings 接口新增 422（LOW/MEDIUM 不建单） | **破坏性**（语义） | v1 任何风险等级都可建单，v2 拒绝低风险 |
| 14 | C-INT 编号重排（C-INT-02~05 → 03~07） | 文档影响 | 引用编号的文档/测试需同步 |
| 15 | 新增 20 个面向前端/资源接口（A/B/C/D-API） | 向后兼容 | 纯新增路径 |
| 16 | MaintenanceConclusion 新增可选 downtimeMinutes | 向后兼容 | 加可选字段 |
| 17 | shared-enums 新增 10 组枚举键 | 向后兼容 | 新键，不影响旧读取方 |
| 18 | local-api.http 新增 | 向后兼容 | 工具文件（但内容绑定 v2 路径） |
| 19 | docs/06 手册新增 | 向后兼容 | 文档 |
| 20 | 各接口新增 401/403/404/409 响应码声明 | 向后兼容 | 声明更完整，调用方本应容错 |

### A.3 破坏性变更的运行时故障论证（A/B 仍按 v1.1.0 实现）

用 jsonschema（Draft 2020-12 + FormatChecker）做了双向交叉校验，实测结果：

**v1 报文 → v2 接收方（全部失败）：**

```
equipment-status-changed.json
  envelope: schemaVersion: '1.0' does not match '^2\.[0-9]+$'   → 400 拒收
maintenance-conclusion.json
  envelope: schemaVersion: '1.0' does not match '^2\.[0-9]+$'   → 400 拒收
  payload:  'submittedBy' is a required property                 → 400 拒收
warning-raised.json
  envelope: schemaVersion: '1.0' does not match '^2\.[0-9]+$'   → 400 拒收
  payload:  'recommendedAction' is a required property           → 400 拒收
  payload:  'metricSnapshot' is a required property              → 400 拒收
```

具体故障链：

1. **B 按 v1.1.0 发预警**：先撞 URL（`POST /api/v1/warnings` 在 v2 服务上不存在 → 404）；改打新 URL 后报文 `schemaVersion=1.0` 违反 `^2\.[0-9]+$`，且缺 `recommendedAction`/`metricSnapshot` → 400。B 侧未升级则**所有预警事件被拒，C 无法自动建单，E2E 主链路中断**。
2. **C 按 v1.1.0 发维修结论**：旧 URL `/api/v1/maintenance-conclusions` → 404；新 URL 上缺 `submittedBy` → 400。B 的预警闭环状态无法更新。
3. **C 按 v1.1.0 发设备状态变化**：旧 URL → 404；新 URL 上 `schemaVersion=1.0` → 400；若 C 生成的 orderId 不符合 `^WO-[0-9]{8}-[0-9]{4}$` 再叠加 pattern 失败。
4. **A/C 调 GET /api/v1/equipment/{id}**：v2 响应中 `type`/`productionLine` 字段已改名，v1 客户端读取到 undefined → 解析失败；路径参数 `equipmentId` 也被收紧为 `^EQ-[0-9]{6}$`。
5. **D 相关**：v1 调用方若发 `channel: "SMS"` 通知 → v2 枚举校验 400。
6. **凭证**：v1 调用方不带 `Authorization`/`X-Internal-Token` → 服务间接口全部 401。
7. **反向（v2 报文 → v1 接收方）同样失败**：`schemaVersion=2.0` 不匹配 `^1\.[0-9]+$`；且 v1 payload schema 均为 `additionalProperties: false`，`metricSnapshot`/`recommendedAction`/`submittedBy`/`downtimeMinutes` 直接被拒。**两版本事件流互不兼容，无法灰度共存，必须同批切换或做双版本适配层。**

### A.4 建议吸收清单

| 变更项 | 建议 | 理由 |
| --- | --- | --- |
| `contracts/http/local-api.http` | **拆独立 PR 吸收，但先裁剪** | 联调工具本身无语义风险，但当前内容全部指向 v2 路径并要求 JWT/内部令牌；直接吸收到 v1 基线会产生与 v1 openapi 不符的假联调脚本。应在 PR 中把请求裁剪为 v1 路径版本，或与 v2 路径吸收同步落地 |
| `docs/06_详细接口约定与联调手册.md` | **拆独立 PR 吸收，标注状态** | 内容质量高（状态机、幂等、错误码、E2E 顺序），但描述的是 v2 目标态（20 接口、8 状态工单机、枚举体系）。合入 main 前需在前言标注"目标态文档，当前基线为 v1.1.0"，避免 A/B 按 v2 实现 |
| 事件收发接口（202/409/幂等语义） | **v1 基线保持现状** | 语义在 v1.1.0 已冻结且兼容；v2 的路径改名 + schemaVersion 升级属于破坏性变更，不得混入 |
| MaintenanceConclusion 新增可选 `downtimeMinutes` | **拆独立 PR** | 向后兼容（加可选字段），但需提供方(C)+调用方(B)双确认；建议与 submittedBy 等工单字段一起由 C 在 Wave 3 前统一提案 |
| contractVersion 2.0.0 + 10 组新枚举 + 7 个 C-API | **退回，由 C 拆小 PR 走契约变更流程** | 一次性大契约会让 A/B 无法跟进（本报告 A.3 已实证互不兼容）；且 `notificationChannel` 顺带删 SMS 属于未声明的破坏性变更，必须单独评审 |
| schemaVersion ^2 / traceId 8 / required 扩充 / 路径改名 / 认证体系 | **退回** | 全部为破坏性变更，需四方排期同步升级或明确双版本策略后再议 |
| `scripts/check_repo.py` 增强（+127 行） | **审查后吸收，但必须先中性化** | 功能性增强有价值（幂等键检查、$ref 检查、版本一致、枚举对照），但多处写死 v2 专属数字，直接合入会打挂 main 的 CI 质量门（见 C 部分实测） |
| `apps/maintenance/` 全部实现代码 | **留待 Wave 3** | 按既定波次方案，由 C 在自己模块分支适配 v1.1.0 后重新提交 |

---

## B. 枚举一致性检查

对 **v1.1.0（当前 main 工作区）** 与 **v2 分支** 分别检查了 shared-enums / openapi / payload schema / examples 四层。

### B.1 v1.1.0 基线（当前仓库）

一致性矩阵（值集合逐层比对）：

| 枚举 | shared-enums | openapi schema | payload schema | 示例取值 | 结论 |
| --- | --- | --- | --- | --- | --- |
| equipmentStatus | 5 值 | EquipmentStatus 5 值 | targetStatus 5 值 | MAINTAINING | 一致 |
| riskLevel | 4 值(code) | RiskLevel 4 值 | riskLevel 4 值 | HIGH | 一致 |
| eventType | 3 值 | —（事件 const） | envelope 3 值 | 三示例各取其一 | 一致 |
| sourceMember | 4 值 | — | envelope 4 值 | MEMBER_B/MEMBER_C | 一致 |
| 维修结果 | （无键） | （内联于 MaintenanceConclusionPayload） | result 3 值 | RECOVERED | 仅 schema 层定义 |
| workOrderStatus | 9 值 | **无对应 schema** | — | — | 悬空定义（见 B.3-1） |
| notificationChannel | **无键** | NotificationChannel 3 值(含 SMS) | — | （无通知示例） | openapi 独有（见 B.3-2） |

- contractVersion `1.1.0` == openapi `info.version 1.1.0`：**一致**
- 三个示例报文全部通过 envelope + payload schema 的 jsonschema 校验：**通过（0 错误）**

### B.2 v2 分支

- 15 组枚举（equipmentStatus、workOrderStatus、riskLevel、maintenanceResult、notificationChannel、warningStatus、workOrderAction、workOrderPriority、workOrderSource、spareRequestStatus、spareRequestAction、roleCode、permissionCode、eventType、sourceMember）在 shared-enums 与 openapi 间**全部一致**；schema 层与示例取值亦一致
- contractVersion `2.0.0` == openapi `info.version 2.0.0`：**一致**
- 三个示例报文全部通过 v2 schema 校验：**通过（0 错误）**
- `python scripts/check_repo.py --strict`（v2 版检查器）在 v2 分支上 31 项全绿（见 C.3）

**发现 1 处真实不一致：**

- v2 `contracts/openapi.yaml:2166` — `UserAccessContext.permissions` 的 example 为 `[WORK_ORDER_ACCEPT, WORK_LOG_WRITE]`，其中 `WORK_LOG_WRITE` **不在** `PermissionCode` 枚举（21 个值）内。该值是 v1 遗留的自由文本示例，v2 收窄枚举时未同步更新。不影响事件示例校验，但会误导联调与代码生成。
  修复建议：将 example 改为合法值组合，如 `[WORK_ORDER_ACCEPT, WORK_ORDER_MAINTAIN]`；或按业务需要在 `PermissionCode` 中补 `WORK_LOG_WRITE`（走契约变更确认）。

### B.3 v1 基线的结构性缺口（非错误，吸收时需注意）

1. `shared-enums.json` 的 `workOrderStatus`（9 值）在 v1 openapi 中无任何路径/schema 消费——v1 基线没有工单接口，属"提前登记"。v2 已补齐对应 schema（值完全一致），Wave 3 后自然消化；保留即可，建议在 README 注明。
2. v1 openapi 的 `NotificationChannel`（含 SMS）与 `MaintenanceConclusionPayload.result`（内联 3 值）未登记进 `shared-enums.json`（缺 `notificationChannel`、`maintenanceResult` 键）。v2 已把两者登记（notificationChannel 顺带删 SMS——**删值需单独评审**）。
3. v1 openapi `UserAccessContext.permissions` example 同样含 `WORK_LOG_WRITE`（v1 无枚举约束所以不报错），若吸收 v2 枚举需一并处理。

### B.4 修复建议汇总（文件 + 位置）

| 文件 | 位置 | 建议 |
| --- | --- | --- |
| v2 contracts/openapi.yaml | L2166 | example 中 `WORK_LOG_WRITE` 替换为 PermissionCode 合法值（如 `WORK_ORDER_MAINTAIN`） |
| v1 contracts/shared-enums.json | 顶层 | （可选）补登 `maintenanceResult: [RECOVERED, PARTIALLY_RECOVERED, NOT_RECOVERED]`，与 payload schema 对齐 |
| v1 contracts/shared-enums.json | 顶层 | （可选）补登 `notificationChannel` 并与 v1 openapi 的 `[IN_APP, EMAIL, SMS]` 对齐；SMS 去留随 v2 评审结论一并定 |
| v1 contracts/README.md | 使用规则 | （可选）注明 workOrderStatus 为 Wave 3 预登记，暂未在 openapi 暴露 |

---

## C. check_repo.py 改动审查

### C.1 新增校验规则清单（每条在检查什么）

对比 `git diff main origin/docs/api-contract-v2 -- scripts/check_repo.py`（+127 行，v2 版共 359 行）：

| 规则 | 行号（v2 版） | 检查内容 | 中性/写死 |
| --- | --- | --- | --- |
| REQUIRED_PATHS + `contracts/http/local-api.http` | L34 | 必需文件存在 | 绑定 v2 材料是否已吸收 |
| REQUIRED_PATHS + `docs/06_详细接口约定与联调手册.md` | L43 | 同上 | 同上 |
| 路径数量 == 20 | L119-123 | openapi 路径规模 | **写死 v2 规模** |
| operationId 数量 == 24 且唯一 | L147-151 | 操作规模与命名 | **写死 v2 规模** |
| x-contract-id 存在且 24 个唯一 | L152-156 | 每操作契约编号 | **写死 v2 规模**（main openapi 无该扩展字段） |
| x-owner-member 计数 == {A:7, B:5, C:8, D:4} | L158-172 | 负责人分配 | **写死 v2 配比**（main openapi 用的是 x-provider-member/x-caller-member 命名） |
| 写接口（除 login）必须引用 IdempotencyKeyHeader | L128/139-146/173-177 | 幂等键纪律 | 中性，main 可通过 |
| OpenAPI 本地 $ref 全部可解析 | L179-202 | 引用完整性 | 中性，main 可通过 |
| openapi.info.version == contractVersion | L235-239 | 版本对齐 | 中性，main 可通过 |
| 12 组枚举与 openapi schema 逐一对照 | L242-263 | 枚举两方一致 | **半写死**（见下） |
| RiskLevel/EquipmentStatus 三层一致性加入 openapi 层 | L308-330 | 枚举三方一致 | 中性，main 可通过 |

### C.2 v2 专属写死校验（导致 main 基线必挂）

以下校验在 main（v1.1.0 基线）上**必然失败**，属于"检查器被写死为 v2 专属"：

1. **L34、L43** — main 上不存在 `contracts/http/local-api.http` 与 `docs/06_详细接口约定与联调手册.md`
2. **L120** — `len(paths) == 20`：main openapi 只有 6 个路径
3. **L148** — `len(operation_ids) == 24`：main 只有 6 个操作
4. **L153** — `all(contract_ids)` 且 `== 24`：main openapi 未标注 `x-contract-id`
5. **L158-163、L169** — owner 配比 7/5/8/4：main openapi 未标注 `x-owner-member`（计数全 0）
6. **L242-263（enum_pairs）** — 两组在 main 上必失败：
   - `notificationChannel`：main shared-enums 无该键（得 `[]`）≠ main openapi `NotificationChannel`（`[IN_APP, EMAIL, SMS]`）
   - `workOrderStatus`：main shared-enums 有 9 值 ≠ main openapi 无 `WorkOrderStatus` schema（得 `[]`）

### C.3 实测运行结果（三组对照）

**① main 版检查器 @ main 基线（对照，退出码 0）：**

```
[OK] 必需文件齐全
[OK] CODEOWNERS 已配置
[OK] 未发现常见秘密文件
[OK] OpenAPI 版本为 3.1
[OK] 六个跨模块 REST 路径齐全
[OK] OpenAPI operationId 唯一
[OK] 公共枚举版本格式正确
[OK] 事件类型与公共枚举一致
[OK] 四名成员来源枚举一致
[OK] warning-raised.json 契约通过
[OK] equipment-status-changed.json 契约通过
[OK] maintenance-conclusion.json 契约通过
[OK] 风险等级在枚举与 Schema 中一致
[OK] 设备状态在枚举与 Schema 中一致
校验通过：14 项，0 个警告
```

**② v2 版检查器 @ main 基线（退出码 1，7 个错误）：**

```
[OK] CODEOWNERS 已配置
[OK] 未发现常见秘密文件
[OK] OpenAPI 版本为 3.1
[OK] 除登录外的写接口均要求幂等键
[OK] OpenAPI 本地引用均可解析
[OK] 公共枚举版本格式正确
[OK] OpenAPI 与公共枚举版本一致
[OK] equipmentStatus 与 OpenAPI 一致
[OK] workOrderAction 与 OpenAPI 一致
[OK] workOrderPriority 与 OpenAPI 一致
[OK] workOrderSource 与 OpenAPI 一致
[OK] warningStatus 与 OpenAPI 一致
[OK] spareRequestStatus 与 OpenAPI 一致
[OK] spareRequestAction 与 OpenAPI 一致
[OK] maintenanceResult 与 OpenAPI 一致
[OK] roleCode 与 OpenAPI 一致
[OK] permissionCode 与 OpenAPI 一致
[OK] 事件类型与公共枚举一致
[OK] 四名成员来源枚举一致
[OK] warning-raised.json 契约通过
[OK] equipment-status-changed.json 契约通过
[OK] maintenance-conclusion.json 契约通过
[OK] 风险等级在枚举、Schema 与 OpenAPI 中一致
[OK] 设备状态在枚举、Schema 与 OpenAPI 中一致
[ERROR] 缺少必需文件：contracts/http/local-api.http, docs/06_详细接口约定与联调手册.md
[ERROR] 预期 20 个路径，实际 6 个
[ERROR] operationId 应有 24 个且不得重复，实际 6 个
[ERROR] 每个操作必须有唯一的 x-contract-id
[ERROR] 接口负责人数量不一致：{'MEMBER_A': 0, 'MEMBER_B': 0, 'MEMBER_C': 0, 'MEMBER_D': 0}
[ERROR] workOrderStatus 与 OpenAPI WorkOrderStatus 不一致
[ERROR] notificationChannel 与 OpenAPI NotificationChannel 不一致
校验失败：7 个错误，0 个警告
```

**③ v2 版检查器 @ v2 分支（退出码 0，31 项全绿）**——证明 v2 检查器与 v2 契约自洽，问题只在于它与 main 基线不兼容。

**结论：改动后的 `check_repo.py --strict` 在 main 基线上不能通过（7 个错误）。** 由于 `.github/workflows/team-quality-gate.yml` 在每个 PR/push 上运行 `python scripts/check_repo.py --strict`，若把 v2 版检查器直接合入 main，所有后续 PR 的 CI 都会红。

### C.4 需要修改的行号与建议改法（待负责人确认，未直接修改）

| 行号（v2 版 check_repo.py） | 现状 | 建议改法 |
| --- | --- | --- |
| L119-123 | `len(paths) == 20` | 改为中性下限断言，如 `len(paths) >= 6` 或仅要求"至少存在一个路径"；规模断言交给契约 PR 自身的评审 |
| L147-151 | `... == 24` | 保留"唯一性"，去掉绝对数量：`len(operation_ids) == len(set(operation_ids)) and operation_ids` |
| L152-156 | `len(contract_ids) == len(set(contract_ids)) == 24 and all(...)` | 去掉 `== 24`，保留"存在且唯一"；或仅当文件中存在任一 `x-contract-id` 时才要求全量一致 |
| L158-172 | 写死配比 `{A:7,B:5,C:8,D:4}` | 改为校验"每个 `x-owner-member` 取值 ∈ {MEMBER_A..D}，且每位 owner 至少 1 个操作"；配比断言删除 |
| L34、L43 | 必需 `local-api.http`、`docs/06` | 与吸收决策绑定：若这两个文件在 Wave 0 先合入 main（裁剪版），保留；否则先从 REQUIRED_PATHS 移除，随文件吸收 PR 再加回 |
| L242-263 | 12 组枚举硬对照 | 改为"两侧都存在才比对"：`if json_name in enums and openapi_name in openapi_schemas: require(json_values == openapi_values)`，可天然兼容 v1 基线 |
| L128/139-146/173-177、L179-202、L235-239、L308-330 | 幂等键、$ref、版本一致、三层枚举 | **保留**（中性规则，main 上实测通过，价值高） |

---

## 总体结论

1. **v2 契约自身质量良好**：内部 15 组枚举四层一致、示例全过校验、检查器自洽（31 项全绿）。
2. **但 v2 对 v1.1.0 是全面破坏性升级**：13 项破坏性变更中任一项都足以打断 A/B 的现有实现；交叉校验实证两版本事件流互不兼容（双向 100% 拒收），无法灰度共存。
3. **吸收顺序建议**：先合"中性化后的 check_repo 增强"（独立 PR）→ 再裁剪吸收 docs/06 与 local-api.http（独立 PR）→ v2 契约本体（新枚举/路径/收紧）由 C 拆小 PR 逐一走"提供方+调用方"双确认 → `apps/maintenance` 代码留待 Wave 3。
4. **吸收前必须处理**：v2 openapi.yaml:2166 的 `WORK_LOG_WRITE` 非法示例值；`notificationChannel` 删 SMS 需单独评审；`local-api.http`/`docs/06` 内容与 v2 路径绑定，不能原样合入 v1 基线。
