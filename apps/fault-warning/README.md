# 成员 B：故障预警与健康评估

> **AI 预生成说明**：本目录当前为湛卢 IDE 预生成的实现（`feat/d-advance-baseline` 分支，对齐契约 v2.0.0），**待成员 B（kuy-3117）认领与重写**。认领时请按任务书逐文件审查，不满意处直接重写，并在本 README 的「成员认领记录」小节登记日期、改动与理由。

## 模块职责

- 计算或模拟设备健康分、风险等级和疑似故障；
- 生成稳定且唯一的 `WarningId`；
- 向成员 C 发送 `WarningRaised` 事件；
- 接收成员 C 的 `MaintenanceConclusionReported`；
- 根据真实根因和维修效果关闭、修正或标注预警。
- 使用成员 D 的统一身份/通知能力，并配合契约与端到端测试。

## 对外契约

- 发送：`WarningRaised`（C-INT-02）；
- 接收：`MaintenanceConclusionReported`（C-INT-04）；
- 公共定义：`contracts/schemas/`、`contracts/examples/` 和风险等级映射。

## 实现前必须确定

- 风险等级到工单优先级的唯一映射；
- 同一设备连续预警的去重、合并或升级规则；
- 模型版本与每条预警的关联方式；
- 维修结论怎样进入后续评估或模型反馈。

## 建议内部结构

```text
src/
├── domain/          # 预警、健康结果、规则
├── application/     # 评估、发布、关闭用例
├── interfaces/      # 数据输入、事件入口
└── infrastructure/  # 模型、数据库、消息适配
tests/
```

不要在本模块复制设备主档或直接修改维修工单数据库。

## 实现状态（AI 预生成，对齐 v2.0.0）

| 能力 | 路径 / 说明 | 契约 | 状态 |
| --- | --- | --- | --- |
| 健康评估 | `POST /api/v1/health-evaluations` | C-INT-02 | 已实现：evaluationId 幂等（重放返回同结果），HIGH/CRITICAL 自动创建预警 |
| WarningRaised 事件发送 | 评估后后台 `POST` 成员 C `/api/v1/integration/warning-events` | C-INT-03 调用方 | 报文经 `contracts/schemas/warning-raised.payload.schema.json` jsonschema 校验后发送，发送失败不阻塞评估（`event_sent` 标记待重发） |
| 维修结论接收 | `POST /api/v1/integration/maintenance-conclusions` | C-INT-05 | 已实现：EventId 幂等，warningId 不存在 404，`effective=true` 置预警 `RESOLVED`，warningId 为空直接收讫 |
| 预警状态机 | `OPEN → ACKNOWLEDGED/RESOLVED` | warningStatus 公共枚举 | 已实现（模块内使用 OPEN/RESOLVED） |
| WarningId 生成 | `WARN-YYYYMMDD-NNNN`，同设备未关闭预警沿用同一 WarningId | — | 已实现 |

风险评估规则（`src/domain/risk_engine.py`，基线：温度 70°C、振动 4.5 mm/s、电流 12 A；惩罚权重 3 / 15 / 3.5，主导异常源生成疑似故障与建议措施；分级阈值 85/60/30 对应 LOW/MEDIUM/HIGH/CRITICAL，P1-P4 映射取自 `contracts/shared-enums.json` 的 riskLevel.orderPriority）。契约示例样本（78.5°C / 6.2 mm/s / 13.8 A）实测 healthScore 42.7 → HIGH，与示例报文量级一致。

### 启动

```bash
cd apps/fault-warning
python -m pip install -r requirements.txt
# Windows: copy .env.example .env   Linux: cp .env.example .env
uvicorn src.main:app --host 0.0.0.0 --port 8102
```

### 触发一次 HIGH 预警（演示）

```bash
python demo_raise_warning.py
```

脚本使用 `contracts/examples/warning-raised.json` 原报文 POST 到成员 C 的 `/api/v1/integration/warning-events`（携带 X-Internal-Token 与 Idempotency-Key），C 未就绪时打印目标 URL 与报文。

服务间调用需要 `X-Internal-Token`（与四服务共享，取 `INTERNAL_API_TOKEN` 环境变量）。

### 测试

```bash
pytest apps/fault-warning
```

覆盖：评估规则与 P1-P4 映射、evaluationId/EventId 幂等、同设备 WarningId 复用、构造报文与契约示例双通过 schema 校验、维修结论 202/幂等/404/RESOLVED 闭环、令牌与幂等键校验。

## 成员认领记录

| 日期 | 认领人 | 改动与理由 |
| --- | --- | --- |
|  |  |  |
