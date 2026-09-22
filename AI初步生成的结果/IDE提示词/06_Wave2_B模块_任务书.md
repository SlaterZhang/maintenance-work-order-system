# Wave 2：成员 B 故障预警与健康评估模块（kuy-3117）

## 前置条件

Wave 1 已合并（A 的 C-INT-01 可用，便于联调，但不阻塞开发——B 可先用契约示例报文做 stub）。

## 任务范围（cluster: apps/fault-warning/）

实现 v1.1.0 契约中 B 的职责：

1. 风险评估：接收/模拟监测数据 → 计算风险等级（LOW/MEDIUM/HIGH/CRITICAL，映射 P4-P1 优先级，以 shared-enums.json 为准）；
2. `WarningId` 生成：每个预警唯一；同一预警重发保持同一 WarningId（幂等）；
3. 发送 `WarningRaised` 事件到 C（POST 到 C-INT-02 的 `/api/v1/warnings`，B 是调用方）；
4. `POST /api/v1/maintenance-conclusions` —— C-INT-04 接收 C 发来的维修结论，关闭/修正/标注预警；
5. 预警状态机：OPEN → …（warningStatus 以 Wave 0 审定后契约为准；若 Wave 0 未合入 v2 的 warningStatus，则 B 模块内私有实现状态，不上公共契约）。

## 验收（我审查时逐条检查）

- [ ] check_repo.py --strict 通过；模块 pytest 全绿
- [ ] 发送的 WarningRaised 报文与 contracts/examples/warning-raised.json 结构一致，能通过 warning-raised.payload.schema.json 校验
- [ ] 同一设备同一预警重复评估不产生重复 WarningId
- [ ] 收到维修结论后对应预警关闭，且 EventId 幂等
- [ ] README 更新（端口 8102、启动、演示方式：如何触发一次 HIGH 预警）

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c feat/b-fault-warning
git commit -m "feat(b): 实现风险评估与 WarningRaised 事件发送"
git push -u origin feat/b-fault-warning
```

PR 标题：`feat(b): 实现故障预警模块`

## 给湛卢 IDE 的提示词要点（完整版结构同 Wave 1，可复制 05 文件改写）

- 骨架生成：同 Wave 1 的分层结构要求，端口 8102，C 调用方 URL 用环境变量 `MAINTENANCE_SERVICE_URL` `.env.example` 已有）；
- 契约自检：核对 C-INT-04 与 warning-raised schema、examples；
- 附加提示词：「写一个演示脚本 scripts/demo_raise_warning.py，构造一条 HIGH 风险的 WarningRaised 事件 POST 到 C 服务，展示 202 响应与返回的 orderId（C 未就绪时打印目标 URL 与报文即可）」。
