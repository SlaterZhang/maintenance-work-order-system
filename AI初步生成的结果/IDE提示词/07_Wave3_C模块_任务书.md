# Wave 3：成员 C 维修工单与备件管理模块（SlaterZhang）

## 前置条件

Wave 0 已合并（契约基线确认）。

## 现状与策略

你的 `docs/api-contract-v2` 分支已有一版完整实现（domain/state_machine.py、work_order_service.py、spare_service.py、idempotency.py、299 行流程测试等）。策略：

- **契约部分**已按 Wave 0 处理（吸收了联调材料，v2.0.0 大契约拆分待议）；
- **代码部分**：不要直接把旧分支整个合进来。在 `feat/c-maintenance` 新分支上，以 v1.1.0 契约为实现目标，把 v2 分支作为参考代码迁入（你的代码所有权是你的模块，重用完全合理），把任何依赖"v2 专属枚举/C-API-01~07"的部分先收敛到模块内部私有能力，等契约拆分 PR 通过后再解锁对外。

## 任务范围（cluster: apps/maintenance/）

1. 接收 WarningRaised（`POST /api/v1/warnings`，C 为提供方）：同一 WarningId 不重复建单（幂等），返回 202 + orderId；
2. 工单状态机（以 shared-enums workOrderStatus 九态为准）；
3. 备件库存最小实现：申请/预留/领用流水，数量不为负，流水不可抵销;
4. 发送 EquipmentStatusChanged 到 A（C-INT-03，C 为调用方）；
5. 发送 MaintenanceConclusionReported 到 B（C-INT-04，C 为调用方）；
6. 调用 A 的 C-INT-01 查询设备（建单快照）。

## 验收（我审查逐条检查）

- [ ] check_repo.py --strict；pytest 全绿（你的 v2 测试很完整，保留并适配）；
- [ ] 重复 WarningId 重放 → 不重复建单，返回原 orderId（E2E-01 关键断言）；
- [ ] 对外事件报文与 contracts/examples/ 三个示例一致、过 schema 校验；
- [ ] 调 A/B 服务的 URL 走环境变量（EQUIPMENT_SERVICE_URL / WARNING_SERVICE_URL）；
- [ ] README 更新（端口 8103、启动、状态机一览表）。

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c feat/c-maintenance
git commit -m "feat(c): 迁入工单状态机与幂等建单实现"
git commit -m "feat(c): 实现备件库存与领用流水"
git push -u origin feat/c-maintenance
```

PR 标题：`feat(c): 实现维修工单与备件管理模块`

## 给湛卢 IDE 的提示词要点

- 迁移适配：「对比 origin/docs/api-contract-v2 分支 apps/maintenance 的实现与 main 的 contracts v1.1.0，列出所有依赖 v2 契约的代码点（枚举、DTO、URL），给出收敛为 v1.1.0 兼容的改法清单，先不动代码」；
- 幂等加固：「审计 idempotency.py 与建单路径：WarningId 幂等在并发下的竞态（两请求同时到达）如何处理？给出加锁/唯一约束方案」；
- 事件外送：「实现 outbox 式发送：业务写入成功后事件才发送，发送失败保留待发送状态可重试」。
