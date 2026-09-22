# Wave 1：成员 A 设备资产与运行监测模块（Aurora-Alex-Blue）

## 前置条件

- Wave 0 已合并（契约基线确认）。
- 技术栈：**Python 3.12 + FastAPI + pydantic v2 + SQLite（sqlite3 标准库或 SQLAlchemy 2.x 均可，模块内自选但要在 README 注明）**。

## 任务范围（cluster: apps/equipment-monitoring/）

实现 v1.1.0 契约中 A 作为提供方的全部内容：

1. `GET /api/v1/equipment/{equipmentId}` —— C-INT-01 设备查询（C 调用）；
2. `POST /api/v1/equipment-status-events` —— C-INT-03 接收 C 发来的维修状态事件（A 为接收方）；
3. 设备主数据管理（最小 CRUD + 种子数据）：EquipmentId 生成稳定、不复用；
4. 运行状态维护：设备状态机（RUNNING/WARNING/STOPPED/MAINTAINING/TRIAL_RUNNING，与 shared-enums.json 一致）；
5. 模拟监测数据接口（可选加分）：简单时间序列写入/查询，供 B 评估用。

## 必须遵守的契约

- 读 `contracts/openapi.yaml` 中 C-INT-01、C-INT-03 的定义：路径、参数、响应码（200/202/400/404/500/409）、ErrorResponse 结构（code/message/traceId/details）；
- 时间一律 RFC 3339 UTC；
- 事件接收按 EventId 幂等去重；
- 状态枚举只用 `contracts/shared-enums.json` 里的值，禁止代码里私自加枚举。

## 验收（我审查时逐条检查）

- [ ] `python scripts/check_repo.py --strict` 通过
- [ ] `pytest apps/equipment-monitoring` 通过（覆盖率不低于：domain/application 核心路径）
- [ ] 对 `contracts/examples/equipment-status-changed.json` 按契约能 202 接收、重复 EventId 不重复处理
- [ ] 404 时返回结构符合 ErrorResponse schema
- [ ] README 更新了启动方式（uvicorn 命令、端口 8101、种子数据初始化）

## 分支与提交

```bash
git switch main && git pull --ff-only
git switch -c feat/a-equipment-monitoring
# 提交示例：
git commit -m "feat(a): 实现设备查询接口 C-INT-01"
git commit -m "feat(a): 实现维修状态事件接收 C-INT-03"
git push -u origin feat/a-equipment-monitoring
```

PR 标题：`feat(a): 实现设备监测模块`，评审请求 A 的 code owner 之外的至少一名队友（按 CODEOWNERS 自动分配）。

## 给湛卢 IDE 的提示词

见 `05_Wave1_A模块_IDE提示词.md`。
