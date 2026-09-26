# Wave 4a 任务书：补齐看板所需查询接口 + CORS（以产品愿景文档为纲）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 关联章节：第十一章（首页看板：设备总数/正常/预警/故障、设备健康状态列表、今日预警；
> 设备详情：健康度/温度/振动趋势/系统判断/创建维修工单）——这些 UI 全部要靠本波次补的查询接口喂数据。
>
> 前置状态：feat/d-advance-baseline，四模块 119 测试全绿，E2E 闭环 20 断言全过。
> 已知缺口（验收方盘点）：契约定义了 24 个操作，但"查询类"接口多数未实现——
> A 仅实现单设备查询；B 无任何查询接口；D 无登录接口；四服务均无 CORS。

## 目标

按契约补齐 8 个看板必需接口 + 四服务 CORS + 1 个崩溃点修复，使前端看板（下一波次）
能从浏览器直接拉到全部所需数据。

## 接口清单（全部严格按 contracts/openapi.yaml 的 schema 实现，不许自造字段）

| 服务 | 接口 | 契约号 | 看板用途 |
| --- | --- | --- | --- |
| A | GET /api/v1/equipment（分页+状态过滤） | A-API-01 | 首页设备卡片/统计数字 |
| A | GET /api/v1/equipment/{id}/telemetry | A-API-04 | 设备详情趋势图 |
| A | POST /api/v1/equipment/{id}/telemetry | A-API-05 | 模拟器注入运行数据 |
| B | GET /api/v1/warnings（分页+状态过滤） | B-API-01 | 今日预警列表 |
| B | GET /api/v1/warnings/{warningId} | B-API-02 | 预警详情（E2E-03 真断言前提） |
| B | POST /api/v1/warnings/{warningId}/acknowledgements | B-API-03 | 确认预警操作 |
| D | POST /api/v1/auth/login | D-API-01 | 看板登录换 JWT |
| D | GET /api/v1/users/me/access-context | D-API-02 | 当前用户权限上下文 |

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"
（业务愿景 docs/工业设备智能运维与预测性维护系统.md，先通读第十一 章——下一波次要做的
看板 UI 全靠本次接口喂数据）。四个 FastAPI 服务已能一键启动、E2E 闭环已通，但看板所需的
"查询类"接口大多未实现。你的任务：按契约补齐 8 个接口 + CORS + 1 个崩溃点修复。

一、必读文件（先读后写，禁止凭空猜）：
- contracts/openapi.yaml：上述 8 个接口的路径、参数、请求/响应 schema、错误码、
  分页参数命名（pageSize/pageToken 或页码，以契约为准）、x-contract-id；
- 各模块现有代码风格：apps/equipment-monitoring/src/interfaces/http/equipment.py、
  apps/fault-warning/src/interfaces/http/evaluations.py、
  apps/integration-quality/src/interfaces/http/identity.py、各模块 domain/models.py、
  infrastructure/db.py、interfaces/http/deps.py（认证依赖怎么写的）；
- apps/equipment-monitoring/src/domain/models.py：注意 Equipment 实体当前没有健康度字段，
  健康度数据在 B 侧，看板自行联表，本次不要给 A 加健康度字段；
- apps/fault-warning/src/domain/models.py：Warning 实体的状态枚举与已有关联字段。

二、实现清单：
1. A 模块（apps/equipment-monitoring）：
   a. GET /api/v1/equipment —— A-API-01 分页查询设备（支持 status 过滤，schema 照契约）；
   b. GET /api/v1/equipment/{id}/telemetry —— A-API-04 查询运行数据（分页、时间倒序）；
      若 A 的数据库尚无 telemetry 表/实体，按契约 TelemetrySample 结构建表（models.py 加实体 + db.py 建表）；
   c. POST /api/v1/equipment/{id}/telemetry —— A-API-05 批量接收运行数据（存库即可，
      不需要触发任何联动——评估是看板模拟器显式调 B 的，保持服务自治）。
2. B 模块（apps/fault-warning）：
   a. GET /api/v1/warnings —— B-API-01 分页查询预警（支持 equipmentId/status 过滤）；
   b. GET /api/v1/warnings/{warningId} —— B-API-02 预警详情；
   c. POST /api/v1/warnings/{warningId}/acknowledgements —— B-API-03 确认预警
      （状态机：OPEN → ACKNOWLEDGED，参考契约 warnings 状态枚举）。
3. D 模块（apps/integration-quality）：
   a. POST /api/v1/auth/login —— D-API-01：校验种子用户名/密码（seed.py 里有谁先读），
      签发 JWT（用户名/角色/过期时间，密钥从 .env 读，缺省 dev 值即可）；
   b. GET /api/v1/users/me/access-context —— D-API-02：从 Authorization: Bearer 解析 JWT
      返回该用户权限上下文（复用现有 C-INT-06 的逻辑）。
4. CORS：四个服务的 main.py 全部加 CORSMiddleware（allow_origins=["*"]，
   allow_methods=["*"]，allow_headers=["*"]）——浏览器看板跨端口必需。
5. C 崩溃点（验收方台账遗留）：apps/maintenance/src/application/work_order_service.py:105
   附近 ingest_warning_event 对 payload["warningAt"] 等必填字段裸取，缺字段时 500 崩；
   改为缺必填字段抛 BadRequestError（400），错误码与消息风格对齐该文件现有 errors 用法。
   只改输入校验，不动其他逻辑。

三、测试（写完必须实跑）：
1. 每个新接口至少 2 个 pytest 用例（正常 + 一个边界：404/400/分页），
   加到各模块 tests/ 下（新文件命名 test_equipment_list.py / test_warnings_query.py /
   test_auth.py 等，风格对齐现有 tests）；
2. 四模块全量测试：python -m pytest -q，四模块合计 119+ 全绿，0 失败；
3. 冒烟（服务启动后真实调用，贴完整输出）：
   - GET :8101/api/v1/equipment?pageSize=10 → 3 台种子设备；
   - POST :8101/api/v1/equipment/EQ-000001/telemetry 注入 3 条样本 → GET 查回 3 条；
   - GET :8102/api/v1/warnings?pageSize=10 → 至少能看到历史预警；
   - POST :8104/api/v1/auth/login（种子用户）→ 拿 JWT → GET /api/v1/users/me/access-context 带 Bearer → 200；
   - 对 C 发一条缺 warningAt 的预警事件 → 应 400（不再是 500）；
   - 浏览器预检：curl -s -X OPTIONS 任一服务 /health 带 Origin 头 → 响应头含 access-control-allow-origin。
4. scripts/e2e_demo.py 不需要改，但必须重跑确认 20 断言仍全过
  （E2E-03 的探测性变通本次先保留，B-API-02 就绪后下一波次再切换为真断言）。

四、约束：
- 严格按契约 schema 响应（字段名、分页结构、错误码逐一对齐 openapi.yaml）；
- 允许改动：A/B/D 三模块 src（新接口 + models 加实体）与 tests（新用例）、
  四个 main.py 的 CORS、C 的 work_order_service.py 输入校验一处、本任务书使用记录；
- 禁止改动：契约文件、scripts/e2e_demo.py、既有测试用例、C 的其他逻辑、
  A 的既有单设备查询/状态事件接口行为；
- 数据库迁移不用 alembic：沿用各模块 init_db 的 create_all 风格，新表自动建；
- 完成后输出：8 个接口的 diff + 新增测试文件清单 + 四模块 pytest 汇总 + 冒烟输出全文 +
  e2e_demo.py 重跑输出。
完成后在本任务书末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. 我实跑四模块全量测试：119+ 全绿、0 失败；
2. 我启动服务后逐个 curl 这 8 个接口：响应结构与 openapi.yaml 的 schema 一致
   （抽 3 个接口做 jsonschema/pydantic 对照校验）；
3. OPTIONS 预检返回 CORS 头（四服务抽查 2 个）；
4. 缺字段预警事件返回 400（带契约风格错误体），不再是 500；
5. e2e_demo.py 重跑 20 断言全过；改动范围 diff 核对（C 只动了校验一处）。

## 使用记录

- 2026-09-26 · 湛卢 IDE · 任务：补齐看板 8 接口 + 四服务 CORS + C 崩溃点修复。
  - **8 个接口**（全部按 openapi.yaml schema 实现）：
    - A-API-01 `GET /api/v1/equipment`（keyword/productionLineId/status 过滤 + page/pageSize → EquipmentPage）；
    - A-API-04 `GET /api/v1/equipment/{id}/telemetry`（from/to 过滤、measuredAt 降序 → TelemetryPage；新增 telemetry_batch/telemetry_sample 两表实体）；
    - A-API-05 `POST /api/v1/equipment/{id}/telemetry`（批次/样本双重校验、batchId 幂等 duplicate、sampleId 去重 → 202 TelemetryIngestionResponse）；
    - B-API-01/02/03 `GET /api/v1/warnings`、`GET /api/v1/warnings/{warningId}`、`POST .../acknowledgements`（OPEN→ACKNOWLEDGED、乐观锁 409、非 OPEN 409；Warning 实体补 acknowledged_by/acknowledged_at 列——旧 member_b.db 需删除后由 create_all 重建）；
    - D-API-01/02 `POST /api/v1/auth/login`（种子用户 user_id + 缺省密码 demo123456，手写 HMAC-SHA256 JWT 无新增依赖）+ `GET /api/v1/users/me/access-context`（Bearer 解析，路由先于 /{userId} 注册）。
  - **CORS**：四个 main.py 加 CORSMiddleware（origins/methods/headers 全 `*`）。
  - **C 崩溃点**：ingest_warning_event 增加 eventId/payload 及 warningId/equipmentId/riskLevel/suspectedFault/recommendedAction/warningAt 必填校验，缺字段返回 400 BAD_REQUEST（契约风格错误体），仅此一处输入校验、未动其他逻辑。
  - **附带修复**：B 的 build_warning_raised_event 与新增 Warning 序列化对 SQLite 读回的 naive datetime 统一补 UTC（与 Wave3 C 侧修复同根因：SQLite DateTime 列丢时区，naive isoformat 过不了 RFC3339 date-time 校验；本机装有 rfc3339-validator 使既有 schema 测试暴露该问题）。修后 B 既有测试全绿。
  - **测试**：新增 test_equipment_list.py（8 例）/ test_warnings_query.py（8 例）/ test_auth.py（7 例）；四模块全量 **A 21 + B 28 + C 75 + D 18 = 142 passed，0 失败**（119 旧 + 23 新）。
  - **冒烟**（清库重启后真实调用）：设备分页返回 3 台种子设备；telemetry 注入 3 条 → 查回 3 条（降序）；评估造预警后 `GET /warnings` 返回 1 条 CRITICAL OPEN；login 返回 JWT（Bearer/7200s/user 上下文）→ me 带 Bearer 200；C 缺 warningAt 事件 400 `payload 缺少必填字段：warningAt`；OPTIONS 预检 A/C 两服务均返回 `access-control-allow-origin: *`。
  - **E2E 重跑**：20 断言全过（0.44s，退出码 0）；**E2E-03 本次已走真断言分支**（B-API-02 就绪，`GET /warnings/{warningId}` 直接返回 RESOLVED，探测性变通自动未触发）。
