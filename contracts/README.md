# 跨模块接口与数据契约

本目录是成员 A、B、C、D 之间的唯一公共契约。任何实现代码、数据库字段或接口文档与这里冲突时，应先通过契约变更 PR 统一结论。成员 D 维护自动校验和联调证据，A/B/C 仍分别对自己的业务语义负责。

## 文件说明

```text
contracts/
├── openapi.yaml                         # REST 接口
├── shared-enums.json                    # 公共枚举和映射
├── http/
│   └── local-api.http                   # VS Code 可直接执行的联调请求
├── schemas/
│   ├── event-envelope.schema.json       # 所有事件的公共包络
│   ├── warning-raised.payload.schema.json
│   ├── equipment-status-changed.payload.schema.json
│   └── maintenance-conclusion.payload.schema.json
└── examples/
    ├── warning-raised.json
    ├── equipment-status-changed.json
    └── maintenance-conclusion.json
```

## 七项跨模块逻辑接口

| 编号 | 方向 | 用途 | 权威数据 |
| --- | --- | --- | --- |
| C-INT-01 | A → C | C 查询设备主数据 | `EquipmentId`、设备名称、类型、生产线、状态 |
| C-INT-02 | A → B | A 请求健康评估 | 标准单位的监测样本、健康分和风险等级 |
| C-INT-03 | B → C | B 发送高风险预警 | `WarningId`、风险等级、健康分、指标快照 |
| C-INT-04 | C → A | C 反馈维修状态 | `OrderId`、`EquipmentId`、目标设备状态 |
| C-INT-05 | C → B | C 反馈维修结论 | 根因、措施、效果和完成时间 |
| C-INT-06 | A/B/C → D | 查询身份权限上下文 | `UserId`、角色、组织和权限 |
| C-INT-07 | A/B/C → D | 提交通知任务 | 接收人、模板、渠道和业务标识 |

`openapi.yaml` 还定义了各模块面向前端的资源接口，共 20 个路径、24 个操作。详细业务规则、工单与备件状态机见 `docs/06_详细接口约定与联调手册.md`。身份凭证由 D 统一管理，禁止 A/B/C 分别复制用户密码数据。

## 使用规则

1. 开发前导入 `openapi.yaml`，并从 `examples/` 或 `http/local-api.http` 复制报文，不要口头猜字段。
2. 发送事件时，同一业务事件重试必须保持相同 `eventId`。
3. 接收方先按 `eventId` 幂等去重，再执行业务。
4. 时间使用 RFC 3339 UTC；标识创建后不得改义或复用。
5. 新增字段优先设计为可选并提供默认行为；删除、改类型或改语义应升级主版本。
6. 修改本目录必须使用“契约变更”Issue，并请求受影响成员评审。

## 校验

安装开发依赖后运行：

```bash
python -m pip install -r requirements-dev.txt
python scripts/check_repo.py --strict
```

检查会解析 OpenAPI、枚举和 JSON Schema，并使用 Schema 校验全部示例事件。
