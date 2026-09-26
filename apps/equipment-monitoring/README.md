# 成员 A：设备资产与运行监测

> **AI 预生成说明**：本目录当前为湛卢 IDE 预生成的实现（`feat/d-advance-baseline` 分支，对齐契约 v1.1.0），**待成员 A（Aurora-Alex-Blue）认领与重写**。认领时请按任务书逐文件审查，不满意处直接重写，并在本 README 的「成员认领记录」小节登记日期、改动与理由。

## 模块职责

- 维护设备主数据及稳定的 `EquipmentId`；
- 接入、保存或模拟运行监测数据；
- 提供设备当前状态和基础档案查询；
- 接收成员 C 的维修状态事件并更新设备状态；
- 向成员 B 提供健康评估所需的、经约定的监测数据。
- 使用成员 D 提供的统一权限上下文，并配合契约与端到端测试。

## 对外契约

- 提供：设备列表、新建、详情、修改和监测数据接口（A-API-01 至 A-API-05）；
- 提供：`GET /api/v1/equipment/{equipmentId}`（C-INT-01）；
- 调用：`POST /api/v1/health-evaluations`（C-INT-02）；
- 接收：`POST /api/v1/integration/equipment-status-events`（C-INT-04）；
- 公共定义：`contracts/openapi.yaml` 和 `contracts/shared-enums.json`。

完整路径、DTO、状态码和示例请求见 `docs/06_详细接口约定与联调手册.md` 与 `contracts/http/local-api.http`。本模块本地端口固定为 `8101`。

## 实现前必须确定

- 设备主数据的最小字段和唯一性规则；
- 监测数据时间戳、单位、采样频率和缺失值规则；
- 状态更新的幂等与并发处理；
- 模拟数据和真实数据的隔离方式。

## 建议内部结构

请根据最终技术栈调整，但保持模块边界：

```text
src/
├── domain/          # 设备、状态等业务对象
├── application/     # 查询与状态更新用例
├── interfaces/      # HTTP/事件入口
└── infrastructure/  # 数据库、消息和外部设备适配
tests/
```

不要在本模块实现工单派发、备件审批或风险模型业务。

## 实现状态（AI 预生成，对齐 v1.1.0）

| 能力 | 路径 / 说明 | 契约 | 状态 |
| --- | --- | --- | --- |
| 设备主数据查询 | `GET /api/v1/equipment/{equipmentId}` | C-INT-01 | 已实现，404/500 返回 ErrorResponse 结构 |
| 维修状态事件接收 | `POST /api/v1/equipment-status-events` | C-INT-03 | 已实现，EventId 幂等去重，报文按 `contracts/schemas/` 做 jsonschema 校验 |
| 设备主数据 | SQLite（SQLAlchemy 2.x），`MEMBER_A_DATABASE_URL` 配置 | — | 3 台种子设备：EQ-000001（RUNNING）、EQ-000002（STOPPED）、EQ-000003（TRIAL_RUNNING） |
| 状态机 | `currentStatus` 仅取 `contracts/shared-enums.json` 的 `equipmentStatus`，事件接收后置为 `targetStatus` 且 `version` +1 | — | 已实现 |

未实现（后续按需）：监测时间序列接口（任务书可选项）。

### 启动

```bash
cd apps/equipment-monitoring
python -m pip install -r requirements.txt
# Windows: copy .env.example .env   Linux: cp .env.example .env
uvicorn src.main:app --host 0.0.0.0 --port 8101
```

### 测试

```bash
pytest apps/equipment-monitoring
```

测试用例直接以 `contracts/examples/equipment-status-changed.json` 为样例，覆盖 202 接收、重复 EventId 幂等、schemaVersion/枚举/必填字段校验、Idempotency-Key 一致性、404 与 traceId 生成。

## 成员认领记录

| 日期 | 认领人 | 改动与理由 |
| --- | --- | --- |
|  |  |  |
