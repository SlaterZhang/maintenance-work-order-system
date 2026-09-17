# Git 分支与提交规范

## 1. 分支模型

四人课程项目采用轻量主干开发：

- `main`：始终保持可构建、可测试；
- `feat/*`、`fix/*`、`docs/*` 等：每个 Issue 一个短期分支；
- 不建立长期 `develop` 或个人总分支，减少反复合并和大冲突。

## 2. 开始开发

```bash
git switch main
git pull --ff-only
git switch -c feat/b-B-FR-05-warning-rule
```

`--ff-only` 可以在本地分支意外偏离远端时停止，而不是自动制造一次难以解释的合并。

## 3. 开发中同步 main

在 PR 合并前同步：

```bash
git fetch origin
git merge origin/main
```

如果团队成员已经熟悉 rebase，也可在自己的、尚未被其他人使用的功能分支上执行：

```bash
git rebase origin/main
```

禁止对 `main` 强制推送；不要 rebase 一个队友也在使用的共享分支。

## 4. 减少冲突的方法

- 一个 PR 只围绕一个 Issue；
- 先确定目录所有权，不跨模块进行无关格式化；
- 公共文件的变更单独提交，方便评审和回滚；
- 数据库迁移文件使用时间戳或递增版本，禁止两人创建同名迁移；
- 自动生成文件由 CI 生成时，不与手写源码混合维护；
- 修改同一契约前先在 Issue 中声明，避免两人同时编辑。

## 5. 冲突处理

```bash
git fetch origin
git merge origin/main

# 修改冲突文件并逐项确认，不要直接选择“全部接受当前/传入”
git add <已解决文件>
git commit
python scripts/check_repo.py
```

涉及别人负责的目录时，解决后必须让该负责人复查。无法判断业务含义时停止解决并在 PR 中提问。

## 6. 提交粒度

推荐：

```text
feat(c): 增加备件申请领域对象
test(c): 覆盖库存不足场景
docs(contract): 补充 SparePartRequest 示例
```

不推荐：

```text
update
改完了
最终版本2
feat: 工单、备件、登录、页面和接口全部完成
```

## 7. 撤销方式

- 未提交的单文件修改：使用编辑器逐项撤销，先确认目标文件；
- 已推送且已被他人使用的提交：新建 PR 执行 `git revert <commit>`；
- 不得在共享分支使用 `git reset --hard` 或强制推送来掩盖历史。
