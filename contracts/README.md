# 跨模块接口与数据契约

本目录是成员 A、B、C、D 之间的唯一公共契约。任何实现代码、数据库字段或接口文档与这里冲突时，应先通过契约变更 PR 统一结论。成员 D 维护自动校验和联调证据，A/B/C 仍分别对自己的业务语义负责。

## 文件说明

```text
contracts/
├── openapi.yaml                         # REST 接口
├── shared-enums.json                    # 公共枚举和映射
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

## 五项逻辑接口

| 编号 | 方向 | 用途 | 权威数据 |
| --- | --- | --- | --- |
| C-INT-01 | A → C | C 查询设备主数据 | `EquipmentId`、设备名称、类型、生产线、状态 |
| C-INT-02 | B → C | B 发送预警事件 | `WarningId`、风险等级、健康分、疑似故障 |
| C-INT-03 | C → A | C 反馈维修状态 | `OrderId`、`EquipmentId`、目标设备状态 |
| C-INT-04 | C → B | C 反馈维修结论 | 根因、措施、效果和完成时间 |
| C-INT-05 | D ↔ A/B/C | 统一身份与通知 | `UserId`、角色、组织、权限和通知渠道 |

当前 OpenAPI 对 C-INT-01 至 C-INT-05 给出可执行契约。身份凭证仍应交由最终选定的认证方案管理，禁止 A/B/C 分别复制用户密码数据。

## 使用规则

1. 开发前从 `examples/` 复制报文做 Mock，不要口头猜字段。
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
