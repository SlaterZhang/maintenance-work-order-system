# Wave 4：成员 D 系统集成、质量保障与交付（zh3g 负责人）

## 任务范围（cluster: apps/integration-quality/ + 根目录工程）

### 4.1 D 服务本体

1. `GET /api/v1/users/{userId}/access-context` —— C-INT-05 统一身份权限（D 为提供方）；
2. 用户/角色种子数据（设备主管、维修工程师、仓管员、管理员）；
3. 统一通知入口（模块内最小实现即可）。

### 4.2 跨模块质量（D 的门禁职责）

1. 四服务 docker-compose.yml（或 scripts/start_all.ps1 + start_all.sh，每人能一键起四个服务）；
2. 端到端测试 tests/test_e2e_scenarios.py：按 docs/04 的 E2E-01~04 走通（可用 fastapi TestClient 组合四服务 + HTTP 桩，或真实起服务请求）；
3. 根目录 README.md 全面重写：项目定位（移动云杯参赛作品）、架构图（ASCII/mermaid）、四服务表格、一键启动、演示流程；
4. E2E 联调记录模板落一份实例（docs/e2e/E2E-01 记录.md）。

### 4.3 交付打包（比赛硬性要求）

1. 作品说明文档骨架 docs/参赛材料/作品说明文档.md —— **严格按附件2六章节**：作品概述/创新性/湛卢原生IDE能力运用/技术实现/应用价值/附件与补充材料；
2. 演示视频脚本 docs/参赛材料/演示视频脚本.md（对应 E2E-01→04 一镜到底流程 + 视频要点）;
3. 打包清单与命名：`团队名称-队长姓名-队长手机号-作品名称.zip`（≤3G，队长上传，含代码+文档+视频+启动说明）。

### 4.4 湛卢 IDE 证据资产（评分章三的弹药库）

- 每个成员在各自 IDE 提示词文件末尾的「使用记录」表格里持续追加；
- Wave 4 时汇总成 docs/参赛材料/湛卢IDE使用总结.md：每条 = 用了什么能力（生成/调试/评审/修bug/测试/Skill/MCP）+ 用在什么环节 + 解决了什么问题 + 证据（diff/截图链接）。

## 验收

- [ ] check_repo.py --strict；全仓 pytest 全绿（含 E2E）；
- [ ] 干净机器按 README 一键启动成功（四服务健康检查）；
- [ ] E2E-01~04 测试全通过并留档 TraceId；
- [ ] 作品说明文档六章齐全、灰色说明文字已清除；
- [ ] 打包脚本产出 zip 且命名合规。

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c feat/d-demo-and-packaging
git commit -m "feat(d): 实现统一身份权限接口 C-INT-05"
git commit -m "feat(d): 增加一键启动与端到端场景测试"
git commit -m "docs(d): 重写项目README与参赛材料骨架"
git push -u origin feat/d-demo-and-packaging
```
