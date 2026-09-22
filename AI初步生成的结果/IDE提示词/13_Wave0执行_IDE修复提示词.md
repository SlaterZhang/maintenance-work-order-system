# 给湛卢 IDE 的提示词 · Wave 0 方案乙：v2 基线切换修复

> 前置：负责人已在 `contract/v2-baseline` 分支上执行完 12 号文件第三节的 `git checkout` 命令（v2 公共文件已取入工作区）。
> 你的任务：把下面提示词交给 IDE，只做两件事——修复 L2166 非法示例值、中性化 check_repo.py。完成后把 diff 和运行输出交回负责人审查。
> 用完在文末追加使用记录。

---

## 提示词 A：修复非法示例值 + 中性化检查器（一次粘贴）

```
你在本仓库的 contract/v2-baseline 分支上工作。工作区已通过 git checkout 从 origin/docs/api-contract-v2 分支取入了 v2 契约与检查器文件。现在只做以下两件事，不改动其他任何文件：

任务1：修复 contracts/openapi.yaml 的非法示例值
- 在 contracts/openapi.yaml 约 L2166 处，UserAccessContext.permissions 的 example 为 [WORK_ORDER_ACCEPT, WORK_LOG_WRITE]，其中 WORK_LOG_WRITE 不在同文件 PermissionCode 枚举（约 L1128 起）的合法值内；
- 把 example 中的 WORK_LOG_WRITE 替换为 PermissionCode 枚举中真实存在、且语义最接近"维修记录"的合法值（先读枚举再选，不要凭空猜）；
- 全文件 grep 确认无其他 WORK_LOG_WRITE 残留。

任务2：中性化 scripts/check_repo.py 的 v2 专属写死校验（依据 wave0-契约审计报告.md 的 C.4 建议）
- L119-123 附近：`len(paths) == 20` 的绝对数量断言 → 改为 `len(paths) >= 6` 的下限断言；
- L147-151 附近：operationId `== 24` 数量断言 → 保留唯一性检查，去掉绝对数量；
- L152-156 附近：x-contract-id `== 24` 断言 → 改为"存在任一 x-contract-id 时才要求全量存在且唯一，否则跳过"；
- L158-172 附近：写死的负责人配比 {A:7, B:5, C:8, D:4} → 改为"每个 x-owner-member 取值必须在 {MEMBER_A..MEMBER_D} 内，且出现的每位 owner 至少拥有 1 个操作"；
- L34、L43 附近：REQUIRED_PATHS 中的 contracts/http/local-api.http 与 docs/06_详细接口约定与联调手册.md 保留（本次 PR 会一并吸收这两个文件）；
- L242-263 附近：12 组枚举硬对照 → 改为"shared-enums 与 openapi 两侧都存在同名枚举时才比对值集合，单侧缺失跳过"，保证未来任一侧增删枚举不会误伤。

完成后的验证（必须实际运行并贴出完整输出）：
1. python scripts/check_repo.py --strict   → 期望 31 项左右全绿、退出码 0
2. python -m unittest discover -s tests -p "test_*.py"  → 若 tests/test_contract_examples.py 因 v2 契约（schemaVersion=2.0、新必填字段）而失败，请同步适配该测试文件到 v2（它校验的是 contracts/examples/*.json 能过 contracts/schemas/*.schema.json，v2 示例与 v2 schema 应天然匹配；若测试写死了 v1 值，改为从 contracts/shared-enums.json 动态读取）
3. grep -rn 'WORK_LOG_WRITE' contracts/ || echo CLEAN
4. python scripts/check_commit_msg.py --text "feat(contract): 切换契约基线至v2并中性化质量门禁"

约束：
- 只允许修改：contracts/openapi.yaml（仅 L2166 一处 example）、scripts/check_repo.py、tests/test_contract_examples.py（仅当且仅当第2步失败时）；
- 禁止改动：contracts/ 其他文件、apps/、docs/、.github/、.githooks/；
- 输出：改动 diff + 上述4条命令的实际运行输出 + 你在 PermissionCode 枚举中选中替代值的理由。
```

---

## 使用记录

| 日期 | IDE能力 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-09-22 | 定点编辑 + 脚本实跑（提示词 A 两任务） | 修复 openapi.yaml L2166 非法示例值（WORK_LOG_WRITE → WORK_ORDER_MAINTAIN）；按审计报告 C.4 中性化 check_repo.py 五处写死校验 | contracts/openapi.yaml、scripts/check_repo.py 的 diff；验证全绿：check_repo --strict 32 项 OK、unittest 1 项 OK、WORK_LOG_WRITE 无残留、提交标题格式通过；tests 无需适配 | 待负责人审查 |
