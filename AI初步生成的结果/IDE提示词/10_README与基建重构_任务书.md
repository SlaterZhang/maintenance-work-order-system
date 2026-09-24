# README 与项目基建重构任务书（负责人 zh3g，可与应急方案并行）

## 问题

根 README.md 目前只有两行"This is a homework project"，与移动云杯参赛作品完全不符。评委/观众看到的第一个文件就是它。

## 任务

在分支 `docs/rewrite-readme` 上重写 README.md，结构如下：

1. **项目名与一句话定位**：工业设备智能运维与预测性维护系统（四服务微服务架构）；
2. **作品信息**：移动云杯 AI Coding 赛道参赛作品（团队信息提交时填）；
3. **系统架构图**：ASCII 或 mermaid，展示 A(8101)/B(8102)/C(8103)/D(8104) 四服务及 C-INT-01~05 五条接口的数据流；
4. **模块分工表**：成员/职责/目录（引用 docs/01 责任矩阵）；
5. **快速启动**：环境要求（Python 3.12）、一键启动命令、四服务健康检查；
6. **核心场景演示**：E2E-01~04 的一句话描述 + 如何复现；
7. **工程化亮点**：契约先行、契约测试门禁、幂等设计、CODEOWNERS 协作流程（这些是现成的加分素材）。

同时：
- 删除 README.md 里 "homework project" 字样；
- `README-TEAM.md` 保留（协作规范入口），在主 README 加链接；
- `.gitignore` 确认包含 `__pycache__/`、`.zhanlu/`（本地 IDE 会话文件不应入库——现在 .zhanlu/ 是 untracked 状态，确认 gitignore 覆盖后它不会再出现在 git status 里）。

## 验收

- [ ] README 六要素齐全，无 "homework" 残留
- [ ] 架构图与实际端口/接口一致（8101-8104，C-INT-01~05）
- [ ] `python scripts/check_repo.py --strict` 通过
- [ ] `git status` 中不再出现 `.zhanlu/`

## 给湛卢 IDE 的提示词

```
请重写本仓库根目录 README.md 为移动云杯参赛作品主页。要求：
1. 先通读 contracts/openapi.yaml（四服务接口与端口）、docs/01_模块边界与责任矩阵.md（分工）、docs/04_完成定义与联调清单.md（E2E场景）；
2. 按以下结构输出中文 README：项目定位（一段）、系统架构（mermaid 图，四个服务 apps/equipment-monitoring:8101、apps/fault-warning:8102、apps/maintenance:8103、apps/integration-quality:8104，箭头标注 C-INT-01 设备查询 A→C、C-INT-02 预警事件 B→C、C-INT-03 维修状态事件 C→A、C-INT-04 维修结论 C→B、C-INT-05 身份权限 D→A/B/C）、模块分工表、快速启动（Python 3.12 + 各模块 pip install + uvicorn 启动命令 + 健康检查 curl）、E2E 场景列表、工程化亮点（契约门禁/幂等/CODEOWNERS）；
3. 只改 README.md，其他文件不动；
4. 禁止编造尚不存在的功能——当前代码实现进度以 git 实际文件为准，未实现的模块描述用"规划中"标注。
```

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c docs/rewrite-readme
# IDE 生成 + 审查后
git add README.md .gitignore
git commit -m "docs(docs): 重写README为参赛作品主页"
git push -u origin docs/rewrite-readme
```
