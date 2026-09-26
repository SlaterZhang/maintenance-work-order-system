# Wave 2 任务书：四服务真实启动冒烟测试（以产品愿景文档为纲）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 关联章节：第十章（Demo 演示：设备模拟器每 5 秒出数，人为制造异常，系统立即响应）、
> 第十一章（首页看板：设备总数/正常/预警/故障，点击设备看详情、健康度、趋势）。
>
> 前置状态：feat/d-advance-baseline 分支，四模块测试 116 passed 全绿，
> C 模块 conftest 已补齐（72/75，3 个失败为 C 代码真 bug，留待其 PR 修）。

## 目标

四个服务作为**真实进程**启动成功并互相可达：每个服务 uvicorn 拉起、/health 探活、
服务间调用（D 的身份接口被 A/B/C 调用）真实走 HTTP 而非 mock。这是 demo 的"点火"步骤。

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"
（业务愿景见 docs/工业设备智能运维与预测性维护系统.md，先通读第十、十一章）。
四个 FastAPI 服务：A 设备监测(8101)、B 故障预警(8102)、C 维修工单(8103)、D 身份通知(8104)。

此前所有测试都是进程内 TestClient，从未真实启动过服务。你的任务：让四个服务作为
真实进程启动起来，并做一轮跨服务冒烟验证。具体要求：

1. 写一个启动脚本 scripts/start_all.ps1（PowerShell）：
   - 每个服务一个后台窗口：uvicorn src.main:app --port <端口>，
     工作目录分别是 apps/equipment-monitoring、apps/fault-warning、
     apps/maintenance、apps/integration-quality；
   - 各服务启动前为其生成独立 .env（若不存在）：DATABASE_URL 指向各自独立的
     sqlite 文件（member_a.db / member_b.db / member_c.db / member_d.db，禁止共用一个库）、
     INTERNAL_API_TOKEN 统一为 dev-internal-token-change-me、
     MEMBER_A_BASE/MEMBER_B_BASE/MEMBER_C_BASE/MEMBER_D_BASE 按端口互指；
   - 启动后轮询各 /health 直到全部 UP（超时 60s 报错并列出哪个服务没起来）；
   - 脚本支持 -Stop 开关杀掉四个进程。
   注意 C 模块 .env 已有 .env.example 可参考；A/D 模块的 src/config.py 里读哪些
   环境变量，以实际代码为准，不要猜。

2. 冒烟验证（必须实际执行并贴完整输出）：
   a) 四个 /health 全部返回 UP；
   b) D 服务的身份接口（C-INT-05）被真实调用一次（用 curl/httpx 直接调 D 端口）；
   c) A 服务的设备查询接口（C-INT-01）被真实调用一次（种子数据 EQ-000001 应存在，
      A 模块的 src/infrastructure/seed.py 里有种子，先读它确认设备编号）；
   d) B 服务的预警评估接口被真实调用一次（对照 contracts/openapi.yaml 的 B 端路径）；
   e) C 服务的预警事件接收接口被真实调用一次（POST /api/v1/integration/warning-events，
      带 X-Internal-Token 与 Idempotency-Key，body 用 conftest 里 warning_event_payload
      的同构数据：EQ-000001、主轴轴承振动异常、healthScore=42、HIGH）——
      预期 202 accepted（此调用会真实触发 C 查 A 的设备接口，跨服务链路打通）。

3. 产出：
   - scripts/start_all.ps1 全文；
   - 五步冒烟的完整命令与输出（包括失败情况也要贴）；
   - 若任何服务起不来，贴出其终端完整报错，定位到具体行再修——只允许修
     阻碍启动的问题（如缺失依赖、端口冲突、.env 缺失），不允许改业务逻辑。

4. 约束：
   - 只允许新增 scripts/start_all.ps1 与各服务目录下的 .env / .env.example（如缺）；
   - 不允许修改任何 src/ 业务代码（除非它真的无法启动，此时先报告再最小修改）；
   - .env 不入库（确认各服务 .gitignore 覆盖 .env，只提交 .env.example）；
   - 完成后在 AI初步生成的结果/IDE提示词/15_Wave2_四服务启动冒烟_任务书.md
     末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. `scripts/start_all.ps1` 一条命令四服务全部 UP（60s 内）；
2. 五步冒烟输出齐全，其中 e) 预警事件 202 必须真实发生（不是 mock）；
3. 各服务独立数据库文件（无共用）；
4. .env 未入库、.env.example 已提交；
5. 除启动脚本与 .env.example 外无其他文件改动（git status 核对）。
