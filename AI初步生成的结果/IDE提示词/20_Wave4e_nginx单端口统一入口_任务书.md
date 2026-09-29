# Wave 4e 任务书：nginx 单端口统一入口（公网只开一个服务端口）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 背景：Wave 4d 已交付 Debian start_all.sh（四服务绑 0.0.0.0 直连，需开 8101~8104 四个入站端口）。
> 本波次目标：公网只开放一个端口（默认 80），四服务与看板全部经 nginx 统一入口，
> uvicorn 退回仅绑 127.0.0.1，把暴露面从 4 端口缩到 1 端口。
>
> 前置状态：feat/d-advance-baseline @ 430e979；scripts/start_all.sh（bash 版）与
> docs/07_服务器部署说明.md 已存在，本波次在其上增量修改。

## 目标架构

```
浏览器 ──> :80 nginx ──┬── /            → web/dashboard.html（静态托管）
                       ├── /a/api/...    → 127.0.0.1:8101（A 设备监测）
                       ├── /b/api/...    → 127.0.0.1:8102（B 故障预警）
                       ├── /c/api/...    → 127.0.0.1:8103（C 维修工单）
                       └── /d/api/...    → 127.0.0.1:8104（D 身份通知）
```

## 交付物

1. `deploy/nginx.conf`：单端口统一入口配置（见下方提示词细节）；
2. `scripts/start_all.sh` 增量修改：uvicorn 绑定地址由写死 0.0.0.0 改为读
   `LISTEN_HOST` 环境变量（默认 127.0.0.1；export LISTEN_HOST=0.0.0.0 可恢复直连模式，
   兼容 4d 已验收的直连用法）；
3. `docs/07_服务器部署说明.md` 增补"单端口 nginx 方案"章节（安装、启用、验证、回退），
   端口清单表更新为"仅 80(+22)"；
4. `web/dashboard.html`：不改代码，但需验证四个地址框填 `http://<IP>/a` 等路径前缀形式时
   页面全链路可用（fetch 拼 URL 的方式必须兼容 base 带路径）——如果验证发现拼接问题，
   允许最小修补（只动 URL 拼接，不动其他逻辑）。

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"，
四个 FastAPI 服务（A 8101 / B 8102 / C 8103 / D 8104），已有 scripts/start_all.sh
（Debian 一键启停，当前 uvicorn 绑 0.0.0.0）与 docs/07_服务器部署说明.md。
目标：公网只开放一个端口（80），四服务与前端看板全部经 nginx 统一入口，
uvicorn 退回仅绑 127.0.0.1。

先读这些再动手：
- scripts/start_all.sh（重点：uvicorn 启动参数与 .env 生成逻辑）；
- web/dashboard.html（重点：四个服务地址框如何被读取、fetch URL 如何拼接——
  必须确认 base 为 http://IP/a 这种带路径前缀形式时，最终请求是 /a/api/v1/...）；
- docs/07_服务器部署说明.md（现有手册结构，保持风格一致地增补）。

你的任务：

一、创建 deploy/nginx.conf：
   1. listen 80；server_name _;
   2. location / → 静态托管仓库 web/ 目录（root 指向需用注释说明部署时按实际
      clone 路径调整，或用相对说明），默认首页 dashboard.html；
   3. 四个代理：location /a/ → proxy_pass http://127.0.0.1:8101/（注意结尾斜杠，
      剥掉 /a 前缀，后端只见 /api/v1/...），/b/ → 8102、/c/ → 8103、/d/ → 8104；
      proxy_set_header Host $host; X-Real-IP / X-Forwarded-For 按惯例；
   4. /health 的处理：四个服务的 /health 也可经 /a/health 等访问（剥前缀后即命中），
      不需要额外规则，验证时用这个路径确认代理通；
   5. 不启用 TLS（比赛演示内网/临时公网足够，保持零证书依赖）。

二、修改 scripts/start_all.sh（最小增量）：
   uvicorn --host 参数由写死 0.0.0.0 改为读 LISTEN_HOST 环境变量，
   默认 127.0.0.1。注释说明两种模式：
   - 默认（nginx 在前）：仅本机回环，公网不可直连；
   - export LISTEN_HOST=0.0.0.0：恢复 4d 直连模式（兼容旧用法与直接测试）。
   其余逻辑（venv/.env/健康检查/stop/status）一律不动。

三、更新 docs/07_服务器部署说明.md：
   增补"方案二：nginx 单端口统一入口"章节：
   apt install nginx → 拷贝 deploy/nginx.conf 到 /etc/nginx/sites-available 并
   ln -s 到 sites-enabled（或 conf.d，按 Debian 默认结构写清楚）→ nginx -t →
   systemctl reload nginx → 验证 curl http://127.0.0.1/a/health 四条全 UP；
   端口清单表更新：入站仅 80（+22 SSH），并注明"需要直连调试时 export
   LISTEN_HOST=0.0.0.0 后另开 8101~8104"。

验证（必须实际执行并贴输出）：
1. bash -n scripts/start_all.sh + shellcheck（如有）；
2. nginx -t 对 deploy/nginx.conf 做语法检查（nginx 可装在 WSL 或说明无法实跑）；
3. WSL 实跑全链路（如环境允许）：
   apt/nginx 装好后启用配置 → LISTEN_HOST 默认启动四服务 →
   curl http://localhost/a/health（经 nginx）四条全 UP →
   curl http://localhost/d/api/v1/auth/login -X POST -H Content-Type:application/json
   -d {"username":"USER-D-001","password":"demo123456"} 拿到 JWT →
   ss -ltn 确认 8101~8104 只监听 127.0.0.1、80 监听 0.0.0.0 →
   浏览器（或 curl）访问 http://localhost/ 能取到 dashboard.html →
   E2E 不受影响（e2e_demo.py 直连 127.0.0.1:810x，照常 20 断言全过）；
4. dashboard.html 前缀模式核验：把地址框填 http://localhost/a 等值，
   确认注入异常→评估→建单→工单流转全链路在"经 nginx"路径下可用
   （curl 模拟页面请求即可：/a/api/v1/equipment、/b/api/v1/health-evaluations 等）。

约束：
- 允许改动：deploy/nginx.conf（新增）、scripts/start_all.sh（仅 --host 一处及其注释）、
  docs/07（增补章节）、web/dashboard.html（仅当 URL 拼接确有问题时最小修补）、
  本任务书使用记录；
- 禁止改动：任何 src/、contracts/、tests/、start_all.ps1；
- 不引入 docker/TLS/新的 Python 依赖。
完成后在本任务书末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. WSL 实跑：nginx 起 → 四服务经 `http://localhost/a|b|c|d/health` 全 UP；
2. `ss -ltn` 确认 8101~8104 仅 127.0.0.1、80 为 0.0.0.0；
3. 浏览器经 `http://localhost/` 打开看板，地址框填 `/a`~`/d` 前缀形式，
   注入异常→建单→流转→恢复绿全链路真实可用；
4. e2e_demo.py 20 断言无回归；`export LISTEN_HOST=0.0.0.0` 直连模式仍可恢复；
5. diff 核对：nginx.conf 新增 + start_all.sh 仅 host 一处 + docs/07 增补 + （如有）dashboard 最小修补。

## 使用记录

- 2026-09-29 · 湛卢 IDE · 任务：交付 `deploy/nginx.conf`（新增）+ `scripts/start_all.sh` 最小增量（LISTEN_HOST）+ `docs/07` 增补方案二章节。**dashboard.html 未改**（`base()` 去尾斜杠 + `api()` 拼接 `base+path`，前缀形式 `http://<IP>/a` 天然拼出 `/a/api/v1/...`，实测通过，无需修补）。
  - **nginx.conf**：listen 80 / server_name _；`location /` 静态托管 web/（root 绝对路径带部署注释，默认 `/opt/maintenance-work-order-system/web`，index dashboard.html）；`/a|b|c|d/` 四个 proxy_pass 尾斜杠剥前缀（`/a/api/v1/equipment` → `127.0.0.1:8101/api/v1/equipment`，`/a/health` → 后端 `/health`），Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto 按惯例；无 TLS。
  - **start_all.sh**：常量区新增 `LISTEN_HOST="${LISTEN_HOST:-127.0.0.1}"`（注释说明两模式），uvicorn `--host "$LISTEN_HOST"`，[RUN] 输出显示实际绑定地址；venv/.env/健康检查/stop/status 一律未动。
  - **docs/07**：新增"三、方案二：nginx 单端口统一入口（推荐）"（apt 安装 → sites-available/ims + ln -s sites-enabled + 删 default → nginx -t → systemctl reload → 四条 /a|b|c|d/health 验证 → 看板地址框填 `http://<IP>/a` 前缀形式 → 回退步骤），端口清单表改为"方案二仅 80(+22) / 方案一 8101~8104(+22)"，日常运维补 LISTEN_HOST 说明，FAQ 补 nginx 502/欢迎页/家目录 403 三条。
  - **WSL Ubuntu-22.04 实跑验证**（systemd 已启用，nginx 1.18 经 apt 安装，`nginx -t` syntax ok / test successful）：
    1. `bash -n` + `shellcheck` 双通过；
    2. 默认 LISTEN_HOST 启动：4×[RUN]（绑定 127.0.0.1）+ 4×[OK] UP；
    3. 经 nginx：`/a|b|c|d/health` 四条全 `{"status":"UP",...}`；
    4. `POST /d/api/v1/auth/login`（USER-D-001/demo123456）经 nginx 拿到 JWT（Bearer）；
    5. `ss -ltn`：**80=0.0.0.0、8101~8104 仅 127.0.0.1**；
    6. 前缀模式模拟看板请求经 nginx 全通：`/a/api/v1/equipment`（返回 EQ-000001）、`/b/api/v1/warnings`、`/c/api/v1/work-orders`（X-User-Id）、`/a/.../telemetry`；
    7. `e2e_demo.py` 直连 127.0.0.1:810x：**20 断言全过**（1.89s）；
    8. `export LISTEN_HOST=0.0.0.0` 重启：四端口恢复 0.0.0.0 监听（4d 直连模式可回退）；
    9. 首页 `curl http://localhost/`：修 `chmod o+x ~`（家目录 403，www-data 穿越权限，已补进 FAQ 与部署建议）后 HTTP 200 且含"工业设备智能运维平台"。
  - **改动范围**：`deploy/nginx.conf`（新增）、`scripts/start_all.sh`（仅 host 参数/注释/输出共 3 处）、`docs/07_服务器部署说明.md`（增补）、本使用记录；**未改** dashboard.html、任何 src/、contracts/、tests/、start_all.ps1，未引入 docker/TLS/新 Python 依赖。
