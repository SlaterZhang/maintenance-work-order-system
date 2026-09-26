# Wave 3 任务书：E2E-01~04 业务闭环全链路（以产品愿景文档为纲）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 关联章节：第一章（完整业务逻辑链：传感器→监测→异常→预警→建单→分配→备件→维修→验收→恢复→档案沉淀）、
> 第五章（工单状态流转：待确认→待分配→待维修→维修中→等待备件→待验收→已完成/已取消）、
> 第十章（演示叙事：设备变红→严重预警→自动建单→维修处理→工单完成→设备恢复绿色）。
>
> 前置状态：feat/d-advance-baseline，四服务一键启动可用，冒烟验证通过
> （A/B/C/D 全 UP、B→C 异步建单真实发生、C→A 回调真实发生）。

## 目标

写一个 E2E 演示脚本 `scripts/e2e_demo.py`（或 .ps1，建议 Python+httpx），对**真实运行的四个服务**
完整走一遍愿景文档第十章的演示叙事，作为答辩演示的自动化版本与回归工具。

## E2E-01：严重预警自动建单（文档第十章叙事）
1. GET A `/api/v1/equipment/EQ-000001` 记录初始状态（RUNNING）与 version；
2. POST B `/api/v1/health-evaluations`（92℃/8.5mm·s⁻¹/18.2A/1450rpm——文档演示值）；
3. 断言响应 CRITICAL、healthScore < 40；
4. 轮询 C `/api/v1/work-orders` 直到出现 warningId 对应的新工单（B 异步发 WarningRaised）；
5. 断言工单 status = PENDING_CONFIRMATION、equipmentId = EQ-000001。

## E2E-02：工单全流程人工处置（文档第五章状态机）
对 E2E-01 产生的工单，用 D 种子用户依次（每步带 X-User-Id，权限对齐种子角色）：
CONFIRM → ASSIGN（assigneeId=维修工程师种子用户）→ ACCEPT → START →
SPARE_REQUEST（可选：申请轴承备件，走 APPROVE→ISSUE）→
SUBMIT_FOR_INSPECTION（conclusion 带 rootCause/measures/result/effective/completedAt/downtimeMinutes，
**completedAt 必须是 ISO 时间字符串——注意 C 有已知 bug：DateTime 列收 ISO 字符串会 500，
若触发则按遗留问题修复：work_order_service.py:194 加 fromisoformat 解析，这是本波次唯一允许修的 src 代码**）
→ PASS_INSPECTION。
每步断言：200/202 + 返回的 status 按状态机流转正确。

## E2E-03：维修结论回流（C→B，C-INT-04）
1. PASS_INSPECTION 后断言 B 侧预警被关闭（或状态变为 RESOLVED/已处理）：
   GET B 预警详情接口，对照 contracts/openapi.yaml 的 B 端预警路径；
2. 若 C 的结论上报是异步重试，轮询最多 15s。

## E2E-04：设备状态恢复（C→A，C-INT-03）
1. START 时 A 侧设备应已变为 MAINTAINING（C 主动通知）；
2. PASS_INSPECTION 后设备应恢复 RUNNING（或待验收→停机、验收→恢复，以契约 EquipmentStatusChanged 语义为准）；
3. GET A 设备详情断言 currentStatus 变化轨迹：RUNNING → MAINTAINING → RUNNING。

## 脚本工程要求
- 命令行参数：`--base-a/b/c/d`（默认 127.0.0.1:8101~8104）、`--token`（默认 dev-internal-token-change-me）；
- 每步打印：步骤号 + 请求摘要 + 响应状态 + 关键断言结果（成功打勾、失败打叉并中止，退出码 1）；
- 全部通过结尾打印四场景总结与总耗时；
- 脚本可重复运行（幂等：每次生成新 eventId/uuid，不依赖旧数据）。

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"，
四个 FastAPI 服务（A 设备监测 8101 / B 故障预警 8102 / C 维修工单 8103 / D 身份通知 8104）
已能一键启动（scripts/start_all.ps1）。业务愿景见 docs/工业设备智能运维与预测性维护系统.md
（先通读第一、五、十章），核心叙事：监测→预警→建单→维修→恢复 的完整闭环。

你的任务：编写 scripts/e2e_demo.py，对真实运行的四个服务完整执行四个 E2E 场景
（E2E-01 严重预警自动建单 / E2E-02 工单全流程处置 / E2E-03 维修结论回流B /
E2E-04 设备状态恢复A），作为演示与回归工具。按上方"E2E-01~04"与"脚本工程要求"执行。

关键实现提示：
- 先读以下文件再动手，禁止凭空猜接口结构：
  contracts/openapi.yaml（路径/字段/状态枚举）、
  contracts/examples/warning-raised.json、maintenance-conclusion.json、equipment-status-changed.json、
  apps/integration-quality/src/infrastructure/seed.py（可用用户及其权限）、
  apps/maintenance/src/domain/state_machine.py（合法状态流转与触发动作）；
- B 的健康评估请求体按契约 HealthEvaluationRequest：evaluationId（=Idempotency-Key）、
  equipmentId、requestedAt、sample{sampleId,measuredAt,temperatureC,vibrationMmS,currentA,rotationalSpeedRpm}；
- 工单命令统一 POST /api/v1/work-orders/{orderId}/commands，body 含 action/operatorId/
  expectedVersion（乐观锁，从上次响应取 version）；
- C 已知 bug：SUBMIT_FOR_INSPECTION 的 conclusion.completedAt 是 ISO 字符串直接入 DateTime 列会 500，
  修复 work_order_service.py:194 附近（fromisoformat 解析，注意带 Z 后缀），这是本任务唯一允许的 src 修改；
- E2E-03/04 的回流可能是异步的，轮询断言（B 预警状态、A 设备 currentStatus），超时 15s 算失败。

完成后必须实际运行（服务需已启动）并贴完整输出：
1. powershell -File scripts/start_all.ps1（启动）
2. python scripts/e2e_demo.py（四场景全过则退出码 0）
3. powershell -File scripts/start_all.ps1 -Stop（收尾）
若任何断言失败，贴出失败步骤的完整请求/响应，定位修复（同上，只允许修阻碍闭环的问题，
改完在报告中单列"修了什么、为什么"）。

约束：
- 允许新增/修改：scripts/e2e_demo.py、apps/maintenance/src/application/work_order_service.py
  （仅 completedAt 解析一处）、AI初步生成的结果/IDE提示词/16_Wave3_E2E闭环_任务书.md（使用记录）；
- 禁止改动：契约文件、其他 src 代码、测试文件；
- 完成后输出：脚本全文、三段运行输出、修复说明（如有）、四场景断言清单。
完成后在本任务书末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. 我实跑 `python scripts/e2e_demo.py`：四场景全过、退出码 0；
2. E2E-04 轨迹断言真实成立：A 侧设备 RUNNING→MAINTAINING→RUNNING 全程可查；
3. E2E-03 断言真实成立：B 侧预警状态流转到已关闭/已处理；
4. work_order_service.py 的修改仅 completedAt 解析一处（diff 核对），且 C 模块 75 个测试重跑
   之前失败的 3 个（happy path / reject inspection / conclusion）转绿；
5. 除上述允许清单外无其他文件改动。
