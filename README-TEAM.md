# 四人协作快速入口

本目录是一套可直接放到“工业设备智能运维与预测性维护系统”仓库根目录的协作规范。它不绑定 Java、Python 或前端框架，先统一四个人最容易发生冲突的部分：模块边界、公共标识、接口字段、状态枚举、Git 分支、提交信息、Issue、Pull Request 和自动检查。

接口开发以 [`contracts/openapi.yaml`](contracts/openapi.yaml) 为唯一机器契约，目前冻结 20 个路径、24 个操作。开始编码前，每个人都应先阅读 [`docs/06_详细接口约定与联调手册.md`](docs/06_详细接口约定与联调手册.md)，并用 [`contracts/http/local-api.http`](contracts/http/local-api.http) 验证本模块请求。

## 角色与目录

| 成员 | 负责模块 | 代码目录 | 核心输出 |
| --- | --- | --- | --- |
| A | 设备资产与运行监测 | `apps/equipment-monitoring/` | `EquipmentId`、设备档案、运行状态 |
| B | 故障预警与健康评估 | `apps/fault-warning/` | `WarningId`、风险等级、疑似故障 |
| C | 维修工单与备件管理 | `apps/maintenance/` | `OrderId`、工单状态、备件与维修结论 |
| D | 系统集成与质量保障 | `apps/integration-quality/`、`tests/` | 身份权限、通知、CI/CD、联调与部署 |
| 四人共同 | 公共契约与联调 | `contracts/`、`shared/` | 接口、事件、枚举、端到端验收 |

原则：每个人可以独立修改自己的模块；修改 `contracts/`、`shared/`、数据库公共字段或跨模块状态时，必须由受影响成员评审。

## 第一次使用（仓库负责人执行）

将压缩包内容解压到仓库根目录，然后在 Windows PowerShell 中执行：

```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1 `
  -MemberA GitHub用户名A -MemberB GitHub用户名B `
  -MemberC GitHub用户名C -MemberD GitHub用户名D
```

脚本会生成 `.github/CODEOWNERS`、启用本地 Git hooks，并运行结构与契约检查。之后提交初始化文件：

```powershell
git add .
git commit -m "chore(shared): 初始化四人协作规范"
git push
```

再按 [`docs/05_GitHub仓库设置.md`](docs/05_GitHub仓库设置.md) 配置 `main` 分支保护。

## 每位成员开始一个任务

1. 在 GitHub 新建 Issue，填写需求编号、完成条件和影响模块。
2. 从最新 `main` 创建短期分支。
3. 小步提交，只改当前任务涉及的文件。
4. 推送并创建 Draft Pull Request；完成自测后转为 Ready for review。
5. 自动检查通过、至少一名队友批准、评论全部解决后，使用 Squash merge。

PR 标题也使用提交格式，例如 `feat(c): 实现 C-FR-14 备件查询`。

```powershell
git switch main
git pull --ff-only
git switch -c feat/c-C-FR-14-spare-query

# 开发、测试后
git add apps/maintenance contracts
git commit -m "feat(c): 实现 C-FR-14 备件查询"
git push -u origin feat/c-C-FR-14-spare-query
```

分支格式：`类型/成员-需求编号-短描述`，例如：

- `feat/a-A-FR-03-equipment-status`
- `feat/b-B-FR-05-warning-rule`
- `feat/c-C-FR-14-spare-query`
- `ci/d-contract-quality-gate`
- `fix/shared-event-idempotency`
- `docs/contract-warning-event`

## 合并前的硬规则

- 不直接向 `main` 推送，不在别人的模块里“顺手修改”。
- 不跨模块直连或修改对方数据库，只通过 `contracts/` 中的接口或事件交换数据。
- `EquipmentId` 由 A 维护，`WarningId` 由 B 生成，`OrderId` 由 C 生成，不得复用或自行改义。
- 修改接口字段、枚举或事件格式时，先提交“契约变更 Issue/PR”，再改实现。
- 示例数据、接口文档、实现和测试必须在同一个 PR 中保持一致。
- 密钥、密码、Token、真实个人信息和真实工业数据不得提交；只提交 `.env.example`。

## 本地检查

```powershell
python scripts/check_repo.py
python -m unittest discover -s tests -p "test_*.py"
```

完整规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，接口与字段见 [`contracts/README.md`](contracts/README.md)。
