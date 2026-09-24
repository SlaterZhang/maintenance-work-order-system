# 11 · Git 分支与仓库操作指引（负责人手册）

> 本项目已由 `main@0db10fa` 初始化，远端为 `origin/main`，无需新建仓库。若「新开仓库」指为团队重建一个干净的 GitHub 仓库，见文末附录。

## 一、核心规则（每一步都强制）

1. **所有修改必须新开分支**，PR 合并，Squash merge，禁止直推 main（分支保护开启后物理上不可能直推）；
2. 提交标题格式（被 `.githooks/commit-msg` + CI 强制校验）：
   `type(scope): 4~72字说明`，type ∈ feat/fix/docs/test/refactor/chore/ci/build/perf/revert，scope ∈ a/b/c/d/shared/contract/docs，**结尾不加句号**；
3. 分支命名：`类型/成员-描述`，如 `feat/a-equipment-monitoring`、`docs/rewrite-readme`、`contract/absorb-v2-baseline`；
4. 每个分支只干一件事；public 契约改动（contracts/、shared/）必须单独 PR 且单独提交。

## 二、日常操作模板

```bash
# 开始一个任务
git switch main && git pull --ff-only          # 起点永远是最新 main
git switch -c feat/<成员>-<短描述>              # 新分支

# 开发中小步提交
git add <相关文件>
git commit -m "feat(a): 实现设备查询接口 C-INT-01"

# 同步 main 新进度（别人在合并）
git fetch origin
git merge origin/main                          # 冲突就地解决后 git add + git commit

# 完成
git push -u origin feat/<分支名>
# GitHub 开 PR → 标题同提交格式 → CI 绿 + 一名队友 approve → Squash merge
```

## 三、处理队友的远端分支（Wave 0 吸收 C 的 v2）

```bash
git fetch origin                                # 拉到全部远端引用
git log --oneline main..origin/docs/api-contract-v2   # 看他比你 main 多什么
git diff main origin/docs/api-contract-v2 -- contracts/ # 契约差异审查

# 挑文件吸收（不整支合并）：
git switch -c contract/absorb-v2-baseline main
git checkout origin/docs/api-contract-v2 -- contracts/http docs/06_详细接口约定与联调手册.md
python scripts/check_repo.py --strict           # 跑门禁再提交
git add -A && git commit -m "feat(contract): 吸收v2联调材料到v1基线"
```

## 四、验证环境（每位成员 clone 后一次）

```bash
# Windows PowerShell / git-bash：
python -m pip install -r requirements-dev.txt   # jsonschema + PyYAML
python scripts/check_repo.py --strict           # 应输出 14 项全过
python -m unittest discover -s tests -p "test_*.py"
# 可选：启用本地钩子（bootstrap.ps1 会装，手动装）：
git config core.hooksPath .githooks
```

## 五、负责人首次检查清单（GitHub 网页操作）

- [ ] Settings → Collaborators：邀请 A/B/C 三人（写权限，CODEOWNERS 才生效）
- [ ] Actions 首跑绿 → Settings → Rules → Rulesets（或 Branches）：`main` 启用 Require PR、1 approval、Require status checks（勾 `contract-and-structure`、`pr-title`）、Block force pushes
- [ ] `docs/api-contract-v2` 处理后：合并即删分支，退回则保留并挂 Issue 说明
- [ ] Pull Requests 设置：仅允许 Squash merge、自动删除分支

## 附录：如果是想全新建一个团队仓库

```bash
# 1. GitHub 网页 New repository（团队组织下更佳），不要初始化任何文件
# 2. 本地把现仓库推上去：
git remote rename origin old-origin
git remote add origin <https://github.com/<团队>/<新仓库名>.git>
git push -u origin main
git push origin docs/api-contract-v2            # C 的分支别弄丢
# 3. 网页上按第五节配置权限/保护/协作者
# 4. 其余成员：git clone <新地址> && cd <仓库> && python -m pip install -r requirements-dev.txt
```
