# GitHub 仓库设置

仓库管理员只需配置一次。GitHub 页面名称可能随版本略有变化，核心规则保持不变。

## 1. 邀请成员

在仓库 `Settings → Collaborators` 中邀请另外三人，确认四人都能创建分支和 Pull Request。`CODEOWNERS` 中列出的用户必须对仓库具有写权限，否则 GitHub 不会把他们作为有效负责人。

## 2. 合并方式

在 `Settings → General → Pull Requests`：

- 开启 **Allow squash merging**；
- 建议关闭普通 merge commit，保持 `main` 线性清晰；
- 开启 **Automatically delete head branches**；
- 可开启自动合并，但仍需满足评审和自动检查。

## 3. 保护 main

在 `Settings → Rules → Rulesets` 或 `Settings → Branches` 中，为 `main` 创建规则：

- Require a pull request before merging；
- Required approvals：`1`；
- Dismiss stale pull request approvals when new commits are pushed；
- Require review from Code Owners；
- Require status checks before merging；
- 选择 `contract-and-structure` 和 `pr-title`；
- Require conversation resolution before merging；
- Block force pushes；
- Block deletions；
- 建议管理员也遵守规则，不随意绕过。

首次启用 Required status checks 前，先让工作流在一个 PR 中成功运行一次，使检查名称出现在可选列表。

注意：部分私有仓库的保护能力取决于 GitHub 套餐。如果设置项不可见，应检查账号/组织套餐；在无法启用时，仍要人工坚持“只通过 PR 合并、至少一人评审、检查通过”三条规则。

## 4. CODEOWNERS

运行初始化脚本后会生成 `.github/CODEOWNERS`。检查四人的 GitHub 用户名拼写和大小写，并确保文件随初始化 PR 合入 `main`。GitHub 使用 PR 目标分支上的 CODEOWNERS 自动请求评审。

## 5. Issues 与 Projects

- 开启 Issues；
- 使用随包提供的“功能任务、缺陷报告、契约变更”表单；
- 可建立一个 Project，字段至少包含 Status、Owner、Requirement ID、Iteration；
- 需求结论、阻塞和接口决策写进 Issue/PR，不只保留在群聊。

## 6. Actions 权限

在 `Settings → Actions → General`：

- 允许仓库运行本项目工作流；
- Workflow permissions 使用只读内容权限即可；
- 不要把个人 Token 写进 workflow 文件；确需秘密时使用 GitHub Actions Secrets。

## 7. 官方参考

- [GitHub：About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub：About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [GitHub：Issue form schema](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema)
- [GitHub：Workflows](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflows)
