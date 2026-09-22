# Wave 0 执行版：切换 v2.0.0 契约基线（方案乙）

> 决策：2026-09-22 负责人确认方案乙——以 C 的 `docs/api-contract-v2` 为新契约基线。
> 依据：`wave0-契约审计报告.md`（v2 内部自洽 31 项全绿；v1/v2 双向不兼容；main 无存量代码，切换成本最低点就是现在）。
> 分支：`contract/v2-baseline`（从 main 切出）。

## 一、吸收清单（负责人已审定）

### ① 原样吸收（v2 契约本体）
| 路径 | 说明 |
| --- | --- |
| `contracts/openapi.yaml` | v2.0.0，20 路径 24 操作（先修复 L2166 再吸收，见②） |
| `contracts/shared-enums.json` | 2.0.0，15 组枚举 |
| `contracts/schemas/*.json`（4 个） | schemaVersion ^2 包络与 payload |
| `contracts/examples/*.json`（3 个） | v2 示例报文 |
| `contracts/http/local-api.http` | 联调集合（v2 路径，与新基线一致，可原样吸收） |
| `contracts/README.md` | 七接口说明 |
| `docs/06_详细接口约定与联调手册.md` | 联调手册（描述的就是 v2 目标态，一致） |

### ② 修复后吸收
| 路径 | 修复 | 执行者 |
| --- | --- | --- |
| `contracts/openapi.yaml` L2166 | example 的 `WORK_LOG_WRITE` → `WORK_ORDER_MAINTAIN`（不在 PermissionCode 枚举内） | IDE（提示词见 13 号文件） |
| `scripts/check_repo.py` | 按审计报告 C.4 中性化 7 处写死校验；保留幂等键/$ref/版本一致/三层枚举等中性增强 | IDE（同上） |
| `requirements.txt` | 保留 `-r apps/maintenance/requirements.txt`；Wave 4 四模块各自 requirements 后改为四行汇总 | 负责人 |

### ③ 顺手吸收（无语义风险）
`.env.example`（+API_BASE_URL/INTERNAL_API_TOKEN）、`.github/CODEOWNERS` + `.template`（contracts/shared 改四人共审）、`.github/ISSUE_TEMPLATE/contract-change.yml`、`scripts/bootstrap.ps1`（错误处理增强）。

### ④ 不吸收（留待各自 Wave）
`apps/maintenance/` 全部（Wave 3，C 直接以 v2 分支代码为起点开新分支）；`README-TEAM.md`、`apps/*/README.md`、`docs/01、03` 小改动（随 Wave 3/4 再审）。

## 二、验收标准（我最终把关）

1. 吸收后 `python scripts/check_repo.py --strict` **31 项全绿**（中性化后的检查器 + v2 契约）；
2. `python -m unittest discover -s tests -p "test_*.py"` 通过（注意：根 tests/ 的 v1 契约测试若写死 v1 值需同步适配）;
3. `grep -rn 'WORK_LOG_WRITE' contracts/` 无残留；
4. `git diff contract/v2-baseline origin/docs/api-contract-v2 -- contracts/` 仅剩 L2166 一处差异；
5. CI（team-quality-gate）在 PR 上绿。

## 三、操作步骤（负责人）

```bash
# 1. 建吸收分支
git switch main && git pull --ff-only
git switch -c contract/v2-baseline

# 2. 整体取入 v2 的公共文件（①③类）
git checkout origin/docs/api-contract-v2 -- \
  contracts/ \
  docs/06_详细接口约定与联调手册.md \
  scripts/check_repo.py \
  scripts/bootstrap.ps1 \
  .env.example \
  requirements.txt \
  .github/CODEOWNERS .github/CODEOWNERS.template \
  .github/ISSUE_TEMPLATE/contract-change.yml

# 3. 把修复任务交给湛卢 IDE（提示词在 13 号文件），修复 L2166 + 中性化 check_repo

# 4. IDE 完成后本地验证（见"二、验收标准"逐条跑）

# 5. 提交与推送
git add -A
git commit -m "feat(contract): 切换契约基线至v2并中性化质量门禁"
git push -u origin contract/v2-baseline
# 开 PR，标题：feat(contract): 切换契约基线至v2并中性化质量门禁
# PR 描述中 @三人，注明"依据 wave0-契约审计报告.md，方案乙决策，请各自确认自己模块受影响接口"
```

## 四、基线切换的后续影响（必须同步给全队）

- A/B/D 的实现目标从 v1.1.0 的 6 接口变为 v2.0.0：**事件路径带 `/integration/` 前缀、schemaVersion 必须发 "2.0"、traceId ≥8 字符、WarningRaised 多 3 个必填字段、服务间要带 X-Internal-Token**；
- 所有 Wave 任务书（04/06/08/09 号文件）的"以 v1.1.0 为准"字样由本文件覆盖——**以 contracts/ v2.0.0 为准**；
- C 的 Wave 3 任务从"降级适配 v1"变为"v2 代码直接迁入 + 补 C 模块分支"，工作量大幅下降。

## 五、回滚

PR 合并前随时 `git switch main && git branch -D contract/v2-baseline`。合并后回滚走 revert PR（基线切换是一个原子提交，revert 干净）。
