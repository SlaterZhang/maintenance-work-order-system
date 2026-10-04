# Wave 4f 任务书：身份权限补全（契约 7 角色全覆盖）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 来源 bug：`docs/所有流程路线与bug.md` 末尾 —— “现在现有的身份太少了，要求在 web 界面中补全身份”
> 前置状态：`feat/d-advance-baseline` @ 160c0d0（Wave 4e 已交付）
> 分支建议：`feat/d-wave4f-identity-roles`

## 一、问题（负责人已实测）

共享枚举 `contracts/shared-enums.json` 定义了 **7 个 roleCode**、**21 个 permissionCode**，但落地只覆盖了一半：

| 层 | 现状 | 缺口 |
| --- | --- | --- |
| 契约 `roleCode` | 7 个角色定义齐全 | 无 |
| `apps/integration-quality/src/infrastructure/seed.py` | 只有 4 个用户 / 4 个角色 | 缺 WARNING_ANALYST、MAINTENANCE_SUPERVISOR、INSPECTOR |
| `web/dashboard.html` 登录页 | 只有 4 个快捷身份按钮 | 与 seed 同步缺 3 个 |

后果：答辩/演示时“四身份权限矩阵”演示不全，契约声明了 7 个角色却只能登 4 个，与“契约先行”卖点自相矛盾。

## 二、目标

让 **契约声明的 7 个角色全部可登录、权限与契约职责一致、看板快捷按钮齐全、测试覆盖**，且不破坏现有 4 个身份已经验收的演示流程（流程一~六）。

## 三、方案（角色 → 用户 → 权限 映射）

新增 3 个用户，补足缺口；现有 4 个用户、其 userId 与权限**保持不变**（避免破坏 E2E）。

| roleCode | 中文 | userId | 权限（permissionCode） | 状态 |
| --- | --- | --- | --- | --- |
| SYSTEM_ADMIN | 系统管理员 | USER-D-001 | ADMIN_ALL, USER_ACCESS_READ | 已有，不动 |
| EQUIPMENT_OPERATOR | 设备操作员 | USER-A-001 | EQUIPMENT_READ, EQUIPMENT_MANAGE, TELEMETRY_READ, TELEMETRY_WRITE | 已有，不动 |
| MAINTENANCE_ENGINEER | 维修工程师 | USER-C-002 | WORK_ORDER_READ, WORK_ORDER_ACCEPT, WORK_ORDER_MAINTAIN, SPARE_REQUEST | 已有，不动 |
| WAREHOUSE_MANAGER | 仓管员 | USER-C-003 | SPARE_READ, SPARE_APPROVE, SPARE_ISSUE | 已有，不动 |
| **WARNING_ANALYST** | 预警分析师 | **USER-B-001** | WARNING_READ, WARNING_ACKNOWLEDGE, EQUIPMENT_READ, TELEMETRY_READ | **新增** |
| **MAINTENANCE_SUPERVISOR** | 维修主管 | **USER-C-001** | WORK_ORDER_READ, WORK_ORDER_CONFIRM, WORK_ORDER_ASSIGN, WORK_ORDER_CANCEL, WORK_ORDER_INSPECT, SPARE_READ | **新增** |
| **INSPECTOR** | 验收员 | **USER-C-004** | WORK_ORDER_READ, WORK_ORDER_INSPECT | **新增** |

说明：
- 新增账号沿用现有命名 `USER-<字母>-<三位序号>`，登录密码仍是全局默认密码 `demo123456`（`config.py` 的 `login_default_password`，无需在 seed 里存密码）。
- 权限必须**取自契约 `permissionCode` 的 21 个枚举值**，不得自造。
- 工单操作按钮由 `web/dashboard.html` 按 `WORK_ORDER_*` 权限渲染（见 `ACTIONS` 表），所以主管/验收员加 `WORK_ORDER_INSPECT` 后，登录即可看到“验收通过/验收驳回”。

## 四、交付物

1. `apps/integration-quality/src/infrastructure/seed.py`：新增 3 个用户，使 7 个 roleCode 全覆盖；
2. `web/dashboard.html`：登录页快捷身份区补 3 个按钮（预警分析师 USER-B-001 / 维修主管 USER-C-001 / 验收员 USER-C-004），并校验 7 个按钮的 `title` 与权限描述一致；
3. 测试补充（不改既有断言）：
   - `apps/integration-quality/tests/test_identity.py`：7 个角色各自登录后 `access-context` 返回的 roleCodes/permissions 与本节映射表一致；
   - `apps/integration-quality/tests/test_auth.py`：新增 3 个账号登录成功、错误密码 401。
4. `docs/所有流程路线与bug.md`：该 bug 条目标注为已修复（写明分支/提交）。

## 五、给 GPT / 湛卢 IDE 的提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是“工业设备智能运维与预测性维护系统”，
D 模块（apps/integration-quality）负责身份与权限，前端看板是 web/dashboard.html。

背景：契约 contracts/shared-enums.json 声明了 7 个 roleCode，但种子数据 seed.py 只落地了 4 个，
看板登录页也只有 4 个快捷身份按钮。现在要把身份补全到契约声明的 7 个。

先读这些文件再动手（只读，不要改）：
- contracts/shared-enums.json（roleCode 与 permissionCode 的权威枚举）；
- apps/integration-quality/src/infrastructure/seed.py（现有 SEED_USERS 结构与命名风格）；
- apps/integration-quality/src/application/auth_service.py（登录逻辑：用户名 + 全局默认密码）；
- web/dashboard.html（登录页快捷身份按钮区，约 176~181 行；以及 ACTIONS 权限-按钮映射表，约 288~297 行）；
- apps/integration-quality/tests/test_identity.py 与 test_auth.py（现有测试风格）。

你的任务：

一、修改 seed.py —— 在现有 4 个用户之后，按同样字段结构新增 3 个用户，
    使 7 个 roleCode 全部有对应用户：
    1. user_id=USER-B-001, display_name=预警分析师示例, organization=设备科,
       role_codes=["WARNING_ANALYST"],
       permissions=["WARNING_READ","WARNING_ACKNOWLEDGE","EQUIPMENT_READ","TELEMETRY_READ"],
       enabled=True;
    2. user_id=USER-C-001, display_name=维修主管示例, organization=机加车间,
       role_codes=["MAINTENANCE_SUPERVISOR"],
       permissions=["WORK_ORDER_READ","WORK_ORDER_CONFIRM","WORK_ORDER_ASSIGN","WORK_ORDER_CANCEL","WORK_ORDER_INSPECT","SPARE_READ"],
       enabled=True;
    3. user_id=USER-C-004, display_name=验收员示例, organization=质量科,
       role_codes=["INSPECTOR"],
       permissions=["WORK_ORDER_READ","WORK_ORDER_INSPECT"],
       enabled=True。
    现有 4 个用户一个字都不要动。所有 permission 必须来自契约的 permissionCode 枚举，
    禁止自造新权限名。

二、修改 web/dashboard.html —— 在登录页快捷身份按钮区，按现有按钮的写法
    （onclick="fillUser('...')" + title 描述该角色职责与关键权限）补 3 个按钮：
    预警分析师 USER-B-001、维修主管 USER-C-001、验收员 USER-C-004。
    样式/类名沿用现有按钮，不要新增 CSS。其余逻辑一律不动。

三、补测试（只新增用例，不修改既有断言的期望值）：
    1. test_identity.py：参数化遍历 7 个 userId，
       断言 /api/v1/users/{user_id}/access-context 返回的 roleCodes 与 permissions
       与 seed 一致（且 permissions 全部属于契约 permissionCode 枚举）；
    2. test_auth.py：USER-B-001 / USER-C-001 / USER-C-004 用默认密码登录成功（200，返回 accessToken），
       用错误密码登录 401。

四、更新 docs/所有流程路线与bug.md 末尾该 bug 条目，标注“已修复”。

验证（必须实际执行并贴出输出）：
1. cd apps/integration-quality && python -m pytest -q   （期望：原有 18 条全过 + 新增用例通过）；
2. 在仓库根 python scripts/check_repo.py   （期望：32 项通过、0 警告）；
3. 若环境允许，本地起 D 服务后 curl 验证 USER-B-001 登录并取 access-context，
   贴出返回 JSON（含 roleCodes 与 permissions）。

约束：
- 只改上述 4 类文件，不碰其他模块（apps/equipment-monitoring、apps/fault-warning、apps/maintenance）
  与 contracts/ 下任何契约文件；
- 不改 auth_service.py / 登录逻辑本身（登录靠全局默认密码，seed 无需存密码）；
- 不引入新的第三方依赖；
- 完成后不要自行提交，把 git diff 交回负责人审查。
```

## 六、验收（负责人 Hermes 复验，不采信自报）

- [ ] `apps/integration-quality` 测试：原 18 条 + 新增用例全过（实测贴输出）
- [ ] `python scripts/check_repo.py`：32 项通过、0 警告
- [ ] seed 的 7 个用户 roleCodes 覆盖契约全部 7 个 roleCode
- [ ] seed 出现的每个 permission 都在契约 permissionCode 枚举内
- [ ] `web/dashboard.html` 登录页按钮数 = 7，fillUser 指向的 userId 在 seed 中存在
- [ ] 现有 4 个用户的 userId/权限与 Wave4e 前逐字一致（无回归）
- [ ] 浏览器实测：7 个身份逐一登录，操作按钮渲染符合各自权限
- [ ] `docs/所有流程路线与bug.md` 该 bug 标记已修复

## 七、分支与提交

```bash
git switch feat/d-advance-baseline
git switch -c feat/d-wave4f-identity-roles
# IDE 生成 + 负责人审查通过后
git add apps/integration-quality/src/infrastructure/seed.py web/dashboard.html \
        apps/integration-quality/tests/test_identity.py apps/integration-quality/tests/test_auth.py \
        "docs/所有流程路线与bug.md"
git commit -m "feat(d): 补全契约7角色身份权限与看板快捷登录"
git push -u origin feat/d-wave4f-identity-roles
```

## 八、使用记录（每次用完追加）

| 日期 | IDE/模型 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-10-04 | 湛卢 IDE | Wave4f 身份权限补全 | seed.py 补至 7 用户、dashboard.html 补至 7 按钮、test_identity/test_auth 新增用例、bug 文档标注已修复 | 负责人实测验收通过：pytest 32 passed、check_repo 32项/0警告、8104 实测 7 身份登录与权限、浏览器 7 按钮实测 |
