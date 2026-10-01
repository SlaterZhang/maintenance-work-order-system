# 成员 B：故障预警与健康评估

本地端口 **8102**。实现范围对齐 `contracts/openapi.yaml` **v2.0.0**。

## 1. 模块职责

- 接收成员 A 的监测样本，计算健康分与风险等级（LOW / MEDIUM / HIGH / CRITICAL）；
- 生成稳定且唯一的 `WarningId`；
- 向成员 C 发送 `WarningRaised` 事件；
- 接收成员 C 的 `MaintenanceConclusionReported`，按真实根因和维修效果
  关闭、修正或标注预警；
- 使用成员 D 的统一身份/权限能力（权限码 `WARNING_READ` / `WARNING_ACKNOWLEDGE`）。

不负责：设备主档（A）、工单与备件（C）、用户与通知（D）。
按 `docs/06` 第 3 节，B 只保存 `equipmentId`、`UserId`、`linkedOrderId` 等关联 ID，
**不复制**设备主档、用户表或工单表。

## 2. 已完成的任务

### 2.1 对外提供的接口

| 契约编号 | 方法与路径 | 鉴权 | 实现位置 |
| --- | --- | --- | --- |
| C-INT-02 | `POST /api/v1/health-evaluations` | `X-Internal-Token` | `src/interfaces/http/health_evaluations.py` |
| B-API-01 | `GET /api/v1/warnings` | `X-User-Id` + `WARNING_READ` | `src/interfaces/http/warnings.py` |
| B-API-02 | `GET /api/v1/warnings/{warningId}` | `X-User-Id` + `WARNING_READ` | `src/interfaces/http/warnings.py` |
| B-API-03 | `POST /api/v1/warnings/{warningId}/acknowledgements` | `X-User-Id` + `WARNING_ACKNOWLEDGE` | `src/interfaces/http/warnings.py` |
| C-INT-05 | `POST /api/v1/integration/maintenance-conclusions` | `X-Internal-Token` | `src/interfaces/http/integration.py` |
| 运维 | `GET /health` | 无 | `src/main.py` |

响应字段严格按契约的 `additionalProperties: false` 输出，
可为空字段一律**显式返回 `null`**（不用空字符串代替）。

### 2.2 对外调用的接口（B 是调用方）

| 契约编号 | 目标 | 用途 |
| --- | --- | --- |
| C-INT-01 | `GET {EQUIPMENT_SERVICE_URL}/api/v1/equipment/{equipmentId}` | 评估前确认设备存在 |
| C-INT-03 | `POST {MAINTENANCE_SERVICE_URL}/api/v1/integration/warning-events` | 外送 `WarningRaised` |
| C-INT-06 | `GET {INTEGRATION_SERVICE_URL}/api/v1/users/{userId}/access-context` | 校验权限码 |

### 2.3 交付清单

```text
apps/fault-warning/
├── .env.example                     环境变量示例
├── .gitignore
├── pytest.ini
├── requirements.txt
├── README.md                        本文件
├── src/
│   ├── config.py                    运行配置
│   ├── main.py                      FastAPI 入口与契约错误处理
│   ├── domain/                      领域层（无框架依赖）
│   │   ├── enums.py                 公共枚举 + 模块私有动作枚举
│   │   ├── errors.py                统一错误码（docs/06 第 12 节）
│   │   ├── ids.py                   标识格式、生成与 RFC 3339 归一化
│   │   ├── models.py                SQLAlchemy 持久化模型
│   │   ├── scoring.py               规则评分引擎 rule-engine-1.0.0
│   │   └── state_machine.py         预警状态机与结论映射
│   ├── application/                 用例层
│   │   ├── evaluation_service.py    C-INT-02 评估 + WarningId 分配与去重
│   │   ├── warning_service.py       B-API-01~03 与 C-INT-05 闭环
│   │   ├── event_dispatch.py        outbox 投递与 linkedOrderId 回填
│   │   └── serializers.py           领域对象 -> 契约 DTO
│   ├── infrastructure/
│   │   ├── db.py                    引擎与会话
│   │   ├── idempotency.py           Idempotency-Key 去重（同事务登记）
│   │   └── outbox.py                待发送事件状态机
│   └── interfaces/
│       ├── clients/                 member_a / member_c / member_d
│       └── http/                    deps / payloads / 三个路由模块
├── tests/                           179 个用例，全部通过
└── tools/demo_raise_warning.py      演示脚本
```

`tools/` 而不是仓库根目录的 `scripts/`：按 `.github/CODEOWNERS`，
`/scripts/` 属于成员 D，B 不往里添加文件。

## 3. 关键实现说明

### 3.1 风险评估（`src/domain/scoring.py`）

契约冻结的分段（`docs/06` 第 6 节）**不得自行解释**：

| 健康分 | 风险等级 | 自动建单 | 工单优先级 |
| --- | --- | --- | --- |
| [80, 100] | LOW | 否 | P4 |
| [60, 80) | MEDIUM | 否 | P3 |
| [40, 60) | HIGH | 是 | P2 |
| [0, 40) | CRITICAL | 是 | P1 |

只有 **HIGH / CRITICAL** 会生成 `WarningId` 并向 C 外送事件。

算法：健康分从 100 分开始扣减，四项指标权重之和为 100
（振动 40 / 温度 25 / 电流 20 / 转速 15）。每个指标定义"正常阈值"与"满扣阈值"，
偏离比例 `ratio = (value - normal) / (full - normal)`，扣分 `weight × clamp(ratio, 0, 1)`：

| 指标 | 正常阈值 | 满扣阈值 |
| --- | --- | --- |
| 振动速度 | 3.0 mm/s | 6.0 mm/s |
| 温度 | 70 °C | 90 °C |
| 电流 | 15 A | 30 A |
| 转速偏离额定 1500 r/min | 5 % | 15 % |

扣分权重最大的指标被认定为**疑似故障来源**，决定 `suspectedFault`
与 `recommendedAction`。

**单指标安全下限。** 只做加权求和会有业务漏洞：任何单项权重都小于 40，
于是一台 249 °C 的设备也只扣 25 分、落在 MEDIUM，**不会触发工单**。
因此增加与加权分取小值的严重度上限：

- 任一指标 `ratio >= 1.0`（进入报警区，即达到"满扣阈值"）→ 健康分不高于 `59.9`（至少 HIGH）；
- 任一指标 `ratio >= 1.5`（进入跳闸区）→ 健康分不高于 `39.9`（至少 CRITICAL）。

上限作用在**健康分**上而不是直接改写风险等级，
保证"健康分 → 风险等级"始终严格符合契约表格，两者不会自相矛盾。

用契约 `contracts/examples/warning-raised.json` 的样本
（78.5 °C / 6.2 mm/s / 13.8 A / 1450 r/min）验证：
健康分 49.4 → **HIGH**，疑似故障 **主轴轴承振动异常**，
建议措施 **"建议停机检查主轴轴承及润滑状态"**，与契约示例的语义完全一致。

### 3.2 `WarningId` 生成与去重

格式 `WARN-YYYYMMDD-NNNN`，后缀是**当日递增序号**而不是随机数：
随机数在批量评估时会碰撞，而 `warning_id` 上有唯一约束，
碰撞会把一次评估直接变成 500。序号分配在事务内取当日最大值 +1，
并用 SAVEPOINT 兜住并发下的唯一约束冲突后重试。

去重规则：**同一设备 + 同一疑似故障**，且预警仍处于跟踪状态
（`OPEN` / `ACKNOWLEDGED` / `LINKED_TO_ORDER`）时**复用**原 `WarningId`，
不重复建预警、不重复发事件。这对应 Wave 2 任务书的验收条件
"同一设备同一预警重复评估不产生重复 WarningId"。

### 3.3 预警状态机（`src/domain/state_machine.py`）

状态取值来自 `contracts/shared-enums.json` 的 `warningStatus`；
动作枚举是**模块私有**的（`shared-enums.json` 只冻结了状态，没有定义预警动作）。

```text
(新建) ──► OPEN
             │  ACKNOWLEDGE              ┌────────────────────────┐
             ├──────────────► ACKNOWLEDGED ◄── HOLD_ACKNOWLEDGED ─┤
             │                    │                                │
             │ LINK_TO_ORDER      │ LINK_TO_ORDER                  │
             ▼                    ▼                                │
        LINKED_TO_ORDER ◄─────────┘                                │
             │                                                    │
             ├── ACKNOWLEDGE_LINKED ──► LINKED_TO_ORDER（保留关联，仅记录确认）
             ├── RESOLVE ────────────► RESOLVED
             └── MARK_FALSE_POSITIVE ► FALSE_POSITIVE
```

`RESOLVED` 与 `FALSE_POSITIVE` 是终态，不再接受任何动作。

**为什么需要 `ACKNOWLEDGE_LINKED`。** `docs/06` 第 14 节的真实链路里，
C 收到 `WarningRaised` 后会**立即**建单并回传 `orderId`，
预警几乎瞬间从 `OPEN` 进入 `LINKED_TO_ORDER`。
若只允许从 `OPEN` 确认，B-API-03 在实际联调中将永远无法使用。
因此已关联工单的预警仍可被确认：保留 `LINKED_TO_ORDER`
（"已建单"是更强的事实），只写入 `acknowledgedBy` / `acknowledgedAt`。
"一条预警只能确认一次"由 `acknowledgedAt` 是否为空判定。

### 3.4 维修结论如何闭环（C-INT-05）

| 维修结论 | 目标状态 |
| --- | --- |
| `RECOVERED` 且 `effective = true` | `RESOLVED` |
| `RECOVERED` 且 `effective = false` | `FALSE_POSITIVE` |
| `PARTIALLY_RECOVERED` | `ACKNOWLEDGED` |
| `NOT_RECOVERED` | 状态不变，风险等级**升级一级**（封顶 CRITICAL） |

前三行由 `docs/06` 第 10 节第 5 条直接给出。第四行的"升级一级"是对
"保持打开并允许升级风险"的落地。

**`FALSE_POSITIVE` 的触发条件是本模块的判定**：`docs/06` 冻结了取值但未规定
触发方式。本模块取"结论声称已恢复、但明确标注未生效"——
说明该次预警并未对应一个被真正修复的故障，按"标注为误报"处理。
该决定属 B 的预警语义所有权范围，若团队另有约定可直接调整
`src/domain/state_machine.py::action_for_conclusion`。

其他闭环规则：

- `eventId` 去重，重复事件返回 `duplicate: true` 且不改状态；
- 同一 `orderId` 的结论按 `completedAt` **单调推进**，迟到的旧结论
  只留档、不覆盖状态（`docs/06` 第 9 节）；
- `warningId` 为 `null`（人工报修工单）时正常接收，不改任何预警；
- `warningId` 非空但在 B 中不存在时返回 404 `WARNING_NOT_FOUND`，
  且**不留下结论记录**；
- 每次状态或风险变化都写一条 `warning_status_history`，
  保证"预警如何被关闭/修正/标注"可回溯。

### 3.5 事件外送：outbox 模式

1. 评估用例在**同一个事务**内写入：评估记录 + 预警 + outbox 待发送事件 + 幂等记录；
2. 一次性 `commit`，此时"待发送"已持久化，断电也不丢；
3. 提交之后才尝试投递；
4. 投递成功置 `SENT`，并用 C 返回的 `orderId` 回填 `linkedOrderId`、
   推进到 `LINKED_TO_ORDER`；失败累加 `attempts`，
   达到上限（`EVENT_MAX_RETRIES`，默认 3）置 `FAILED`，否则保持 `PENDING` 可重试。

投递失败**不会回滚**已成立的预警，符合 `docs/06` 第 10 节第 7 条。
`Idempotency-Key` 固定使用 `eventId`，重试时保持不变。

### 3.6 幂等与并发

- **HTTP 层**：`Idempotency-Key` 必填且必须是 UUID。命中幂等时返回
  **第一次处理的状态码与响应体**（`ReplayResult` 带回原始状态码，
  201 的请求不会在重放时退化成 200）；同键不同体返回 409 `IDEMPOTENCY_CONFLICT`。
  幂等记录与业务写入**同事务提交**，不存在"业务已提交、幂等记录丢失"的窗口。
- **业务层**：`evaluationId` 是评估的天然幂等键，重复提交返回首次结果，
  不重新评分、不重复建预警。
- **乐观锁**：预警带整数 `version`；`B-API-03` 提交 `expectedVersion`，
  不一致返回 409 `VERSION_CONFLICT`。

## 4. 配置

变量名与仓库根目录 `.env.example` 保持一致。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MEMBER_B_PORT` | `8102` | 本服务端口 |
| `DATABASE_URL` | `sqlite:///./member_b.db` | 数据库 |
| `INTERNAL_API_TOKEN` | `dev-internal-token-change-me` | 服务间令牌，四个服务必须一致 |
| `EQUIPMENT_SERVICE_URL` | `http://localhost:8101` | 成员 A |
| `MAINTENANCE_SERVICE_URL` | `http://localhost:8103` | 成员 C |
| `INTEGRATION_SERVICE_URL` | `http://localhost:8104` | 成员 D |
| `MODEL_VERSION` | `rule-engine-1.0.0` | 写入每条预警的 `modelVersion` |
| `ALLOW_CLIENT_MOCK` | `true` | 见下方安全说明 |
| `CLIENT_TIMEOUT_SECONDS` | `3.0` | 外部调用超时 |
| `EVENT_MAX_RETRIES` | `3` | outbox 最大投递次数 |

**关于 `ALLOW_CLIENT_MOCK`（安全说明）。** 成员 C 的三个客户端在外部服务不可达时
会静默返回 mock 数据，其中 D 的 mock 直接给出"维修主管"权限，
等于"身份服务一挂，所有人自动获得审批权"，A 的 mock 则会伪造设备档案。
B 侧不复制该行为：mock 降级必须由 `ALLOW_CLIENT_MOCK` 显式打开，
降级时只给 B 接口所需的**最小权限集**（预警分析员），
且置为 `false` 后不可达会直接失败（fail closed）。
**联调、演示与 CI 必须使用 `false` 或真实服务**，
测试进程内已强制为 `false`。

## 5. 启动

```bash
cd apps/fault-warning
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

copy .env.example .env          # 按需修改，尤其是 INTERNAL_API_TOKEN
uvicorn src.main:app --port 8102
```

- Swagger UI：<http://localhost:8102/docs>
- 存活探针：<http://localhost:8102/health>

## 6. 测试方法

### 6.1 运行

```bash
cd apps/fault-warning
pip install -r requirements.txt
pytest -q
```

预期输出：

```text
179 passed
```

单独运行某个文件或某个用例：

```bash
pytest tests/test_scoring.py -q
pytest tests/test_warning_api.py::test_acknowledge_linked_warning_keeps_order_link -q
pytest -k "schema or contract" -q
```

在仓库根目录还需通过团队的契约门禁：

```bash
python -m pip install -r requirements-dev.txt
python scripts/check_repo.py --strict     # 预期：校验通过，exit 0
python -m unittest discover -s tests -p "test_*.py"
```

### 6.2 测试用例构成（179 个）

| 文件 | 用例数 | 覆盖内容 |
| --- | --- | --- |
| `tests/test_scoring.py` | 21 | 契约分段边界（80/60/40 的闭开区间）、四项指标线性扣分与满扣、单指标安全下限、疑似故障来源选取、输出范围与可重复性 |
| `tests/test_state_machine.py` | 38 | `warningStatus` 五个取值的全部合法/非法迁移、终态拒收任何动作、结论→动作映射、风险升级、确认动作选择 |
| `tests/test_health_evaluation.py` | 43 | C-INT-02 四种风险等级、`WarningId` 生成/去重/递增、事件报文结构、outbox 失败保留与重试、达到上限置 `FAILED`、幂等三态、鉴权、设备不存在、字段校验 |
| `tests/test_warning_api.py` | 32 | B-API-01~03 的权限码校验、过滤/分页/排序、契约字段完整性、乐观锁、重复确认冲突、确认已建单预警、幂等重放 |
| `tests/test_maintenance_conclusion.py` | 30 | C-INT-05 四种结论映射、`eventId` 幂等、迟到结论不覆盖、风险升级、状态审计、终态只留档、边界与字段校验 |
| `tests/test_contract_payloads.py` | 15 | 发出的 `WarningRaised` 通过 `contracts/schemas/` 的包络与载荷 JSON Schema 校验、字段集合与契约示例一致、标识正则、枚举与 `shared-enums.json` 一致 |
| **合计** | **179** | |

### 6.3 测试如何隔离外部依赖

- 三个外部客户端（A / C / D）由 `tests/conftest.py` 的 **autouse 夹具**替换为受控实现，
  测试**完全不访问网络**；需要模拟"外部服务不可达"的用例在测试体内再覆盖一次；
- `ALLOW_CLIENT_MOCK` 在测试进程内强制为 `false`，
  任何漏打的桩都会**立刻失败**，而不是静默返回伪造数据；
- 每个用例使用独立的临时 SQLite 文件（`tests/.pytest-data/`，已被 `.gitignore` 忽略），
  请求级 Session 与断言用 Session 是**不同连接**，
  既忠实于生产"每请求一个 Session"，也避免读到旧事务快照。

`tests/conftest.py` **随代码一起提交**：成员 C 的 `tests/conftest.py` 未进入版本库，
导致 `apps/maintenance` 的四个测试文件（630 行）全部无法运行，B 侧不重演该问题。

## 7. 演示：触发一次 HIGH 预警

先启动 B（8102）；若 C（8103）也已启动，可以观察到完整闭环。

```bash
cd apps/fault-warning

# 方式一（推荐）：走完整 C-INT-02 链路，B 评分后自动向 C 外送事件
python tools/demo_raise_warning.py evaluate

# 先看报文，不依赖任何服务：
python tools/demo_raise_warning.py direct
```

`evaluate` 会打印 B 的评分结果（`healthScore=49.4`、`riskLevel=HIGH`、
`warningId=WARN-...`）并回查预警，若 C 已建单则显示 `linkedOrderId`；
C 未就绪时预警仍会成立，事件留在 outbox 中等待重试。

等价的 curl 请求：

```bash
curl -X POST http://localhost:8102/api/v1/health-evaluations \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: local-development-internal-token" \
  -H "X-Trace-Id: trace-20260917-001" \
  -H "Idempotency-Key: 6cb7fef3-bcae-42de-8b57-ef54d3431003" \
  -d '{
    "evaluationId": "590161d4-2c35-4b10-960a-f41ec51b1003",
    "equipmentId": "EQ-000001",
    "requestedAt": "2026-09-17T08:29:55Z",
    "sample": {
      "sampleId": "e51d94ca-5258-4e5a-bccc-99c55cfda001",
      "measuredAt": "2026-09-17T08:29:50Z",
      "temperatureC": 78.5,
      "vibrationMmS": 6.2,
      "currentA": 13.8,
      "rotationalSpeedRpm": 1450
    }
  }'
```

查询预警（前端接口需要 `X-User-Id`，权限由 D 的 `C-INT-06` 提供）：

```bash
curl "http://localhost:8102/api/v1/warnings?riskLevel=HIGH" \
  -H "X-User-Id: USER-B-001" -H "X-Trace-Id: trace-20260917-001"
```

## 8. 已知不一致与后续建议

以下均为**其他模块或团队基建**的问题，B 侧未做改动，仅在此登记：

1. **错误码两套并存。** B 严格遵循 `docs/06` 第 12 节的错误码
   （`VALIDATION_ERROR` / `WARNING_NOT_FOUND` / `VERSION_CONFLICT` /
   `IDEMPOTENCY_CONFLICT` / `INVALID_STATE_TRANSITION` / `AUTH_TOKEN_INVALID` /
   `PERMISSION_DENIED` / `EQUIPMENT_NOT_FOUND`）；
   而 `apps/maintenance` 使用的是 `BAD_REQUEST` / `CONFLICT` /
   `IDEMPOTENCY_KEY_CONFLICT` 等另一套取值。两者都能通过
   `openapi.yaml` 中 `ErrorResponse.code` 的正则，但前端无法统一处理，
   建议由 D 组织契约对齐后一次性收敛。
2. **`apps/maintenance/.gitignore` 被误提交成一段 PowerShell 命令文本**
   （内容是 `@' ... '@ | Out-File -Encoding UTF8 .gitignore`），
   整个忽略规则失效，`*.db`、`.env` 存在被误提交的风险。
3. **`apps/maintenance/tests/conftest.py` 缺失**，该模块 630 行测试无法运行。
4. **CI 不执行任何模块的 pytest。** `.github/workflows/team-quality-gate.yml`
   只运行 `scripts/check_repo.py --strict` 与根目录 `tests/` 的 unittest，
   `apps/*/tests` 从未被执行。建议增加按模块的测试步骤。
5. **契约未定义"预警动作"枚举。** `shared-enums.json` 只有 `warningStatus`，
   因此 B 的 `WarningAction` 保持模块私有，未进入公共契约；
   若将来需要跨模块表达预警操作，需按 `docs/06` 第 17 节走契约变更流程。

## 9. 尚未实现

- **`C-INT-07` 通知外送**：契约里没有"按角色查用户"的接口，
  B 无法在不伪造 `UserId` 的前提下解析收件人，因此暂未接入。
  `src/interfaces/clients/member_d.py::submit_notification` 已就绪，
  待契约补充收件人解析方式后即可启用。
- **定时重试任务**：`src/infrastructure/outbox.py` 已提供
  `pending_events()` 与指数退避 `retry_backoff()`，
  当前由评估/结论用例在请求内触发重试；跨进程的定时补偿
  建议与其他模块统一规划（D 的部署配置范围）。
