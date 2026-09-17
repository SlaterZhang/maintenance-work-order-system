# 成员 A：设备资产与运行监测

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
