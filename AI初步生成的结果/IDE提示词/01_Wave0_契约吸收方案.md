# Wave 0：契约审查与 v2 吸收（负责人：zh3g 发起，全队确认）

## 目标

处理 `origin/docs/api-contract-v2`（C 的未合并分支）。它包含工单模块完整实现（约 5000 行）和一版 contractVersion 2.0.0 的大契约改版（openapi.yaml 从约 400 行扩到 2200+ 行，新增 workOrderAction、warningStatus、spareRequestStatus 等十余个枚举）。

**处理原则**：以 main 的契约 v1.1.0 为基线。C 的 v2 契约属于"单方面大改公共契约"，违反本仓库契约变更规则（需提供方+调用方各一人确认）。不整支合并。

## 吸收决策（需要全队在 Issue 里确认）

| v2 内容 | 决策 | 理由 |
| --- | --- | --- |
| `contracts/http/local-api.http`（联调请求集合） | **保留吸收** | 联调工具，不动语义 |
| 事件收发接口（C-INT-02/03/04 事件 + 202/409/幂等语义） | **保留吸收** | 与 v1.1.0 兼容、E2E 场景必需 |
| `docs/06_详细接口约定与联调手册.md` | **保留吸收**（内容核对后） | 联调文档 |
| C 模块实现代码（apps/maintenance/ 全部） | **留待 Wave 3**，由 C 在自己模块分支重新提交 | 代码先进 C 模块分支，不与契约混在一个 PR |
| contractVersion 2.0.0 + 十余个新枚举 + 7 个 C-API | **暂缓**：由 C 拆成独立小 PR，每条走契约变更流程 | 一次性大契约会让 A/B 无法跟进；拆小逐步合 |
| scripts/check_repo.py 改动（+127 行） | **审查后吸收** | 检查器增强，注意别把 v2 专属校验写死 |

## 操作步骤（负责人）

```bash
git switch main && git pull --ff-only
git switch -c contract/absorb-v2-baseline
# 用 git checkout origin/docs/api-contract-v2 -- <允许清单里的路径> 挑选文件
# 例：git checkout origin/docs/api-contract-v2 -- contracts/http docs/06_详细接口约定与联调手册.md
python scripts/check_repo.py --strict
python -m unittest discover -s tests -p "test_*.py"
git add -A && git commit -m "feat(contract): 吸收C模块联调手册与HTTP集合到v1基线"
git push -u origin contract/absorb-v2-baseline
```

然后开 PR，标题 `feat(contract): 吸收v2联调材料到v1基线`，在 PR 描述里 @ 三位成员逐一确认上表的决策。

## 给 IDE 的提示词（吸收时辅助核对）

见 `02_Wave0_契约吸收_IDE提示词.md`。
