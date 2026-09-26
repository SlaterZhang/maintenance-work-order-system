# 成员 D：系统集成与质量保障

> **AI 预生成说明**：本目录当前为湛卢 IDE 预生成的服务实现（`feat/d-advance-baseline` 分支，对齐契约 v2.0.0），**待负责人（zh3g）安排认领**。根目录工程职责（docker-compose、E2E 场景测试、参赛材料）属于 Wave 4 正式交付，不在本次应急预生成范围。

## 模块职责

- 提供统一身份、角色、权限上下文和通知入口；
- 维护跨模块 OpenAPI、事件 Schema、Mock 数据和契约检查；
- 维护 GitHub Actions、Git hooks、测试入口和质量门禁；
- 组织 A/B/C 的端到端联调并保存版本、`TraceId` 和验证证据；
- 维护部署配置、环境变量清单、日志追踪和基础运行监控；
- 发现接口字段、枚举、状态或版本不一致时阻止不安全合并。

## 对外契约

- 提供：统一用户权限上下文查询（C-INT-05）；
- 提供：统一通知提交接口（C-INT-05）；
- 维护：`contracts/` 校验、`tests/`、`.github/workflows/` 和联调记录；
- 协助但不替代：A/B/C 对各自业务规则和字段语义的最终确认。

## 实现前必须确定

- `UserId`、角色编码、权限粒度和最小权限规则；
- 通知模板、渠道、失败重试和去重策略；
- 三个业务服务的本地端口、环境变量和健康检查；
- CI 中各模块的构建、测试和契约检查命令；
- 端到端测试数据如何初始化、隔离和清理；
- 日志如何通过 `TraceId` 串联，同时避免记录密码、Token 和个人敏感信息。

## 建议内部结构

```text
src/
├── identity/        # 用户、角色与权限上下文
├── notification/    # 通知模板、渠道与发送状态
├── integration/     # 网关、适配与跨模块调用
└── observability/   # 日志、追踪和健康检查
tests/
├── contract/        # OpenAPI/Schema 与兼容性
└── e2e/             # E2E-01 至 E2E-04
```

成员 D 不能为了让测试通过而自行改变 A/B/C 的业务事实。发现冲突时应建立契约变更 Issue，并让对应业务负责人决策。

## 实现状态（AI 预生成，对齐 v2.0.0）

| 能力 | 路径 / 说明 | 契约 | 状态 |
| --- | --- | --- | --- |
| 身份权限上下文 | `GET /api/v1/users/{userId}/access-context` | C-INT-06 | 已实现：不存在或已停用用户 404，roleCodes/permissions 全部经 `shared-enums.json` 枚举自检 |
| 统一通知入口 | `POST /api/v1/notifications` | C-INT-07 | 已实现：Idempotency-Key 幂等（重复返回同 notificationId），templateCode 五值枚举、channel 取 `notificationChannel`（IN_APP/EMAIL），variables 字符串字典、businessReference ≤64 |
| 种子数据 | 4 用户：设备主管（EQUIPMENT_OPERATOR）、维修工程师（MAINTENANCE_ENGINEER）、仓管员（WAREHOUSE_MANAGER）、管理员（SYSTEM_ADMIN） | RoleCode/PermissionCode 枚举 | 已实现（权限组合均取自 PermissionCode 合法值） |
| 未实现 | `POST /api/v1/auth/login`（D-API-01）、`GET /api/v1/users/me/access-context`（D-API-02） | — | 待 JWT 方案确定后补（当前服务间调用走 X-Internal-Token） |

服务间调用统一校验 `X-Internal-Token`（取 `INTERNAL_API_TOKEN` 环境变量，四服务共享同一值）。

### 启动

```bash
cd apps/integration-quality
python -m pip install -r requirements.txt
# Windows: copy .env.example .env   Linux: cp .env.example .env
uvicorn src.main:app --host 0.0.0.0 --port 8104
```

### 测试

```bash
pytest apps/integration-quality
```

覆盖：契约示例用户（USER-C-002）的 access-context 结构、4 角色种子、404/停用用户、通知 202/幂等/SMS 拒绝（v2 已删 SMS）/模板与收件人校验、令牌校验。

## 成员认领记录

| 日期 | 认领人 | 改动与理由 |
| --- | --- | --- |
|  |  |  |
