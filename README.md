# 工业设备智能运维与预测性维护系统

面向智能制造的设备运行监测、故障预警与运维管理平台（2026 移动云杯 AI Coding 赛道参赛作品）。

系统围绕"设备监测 → 故障预警 → 维修工单处置 → 备件与验收 → 恢复运行"的完整业务闭环，由四个 FastAPI 微服务与一个零构建单页看板组成：高风险/严重预警自动创建维修工单，维修结论反向关闭预警并恢复设备状态，全程数据可追溯。

- 契约驱动：`contracts/openapi.yaml`（v2，20 个路径 / 24 个操作）为接口唯一事实源，`contracts/shared-enums.json` 统一 7 个 roleCode / 21 个 permissionCode 等公共枚举；
- 权限完整：7 角色 RBAC，看板操作按钮按登录角色权限动态渲染，服务间调用经 `X-Internal-Token` 校验；
- 质量门禁：四模块 410 项测试全绿（A 54 / B 222 / C 98 / D 36）+ 顶层契约与环境一致性测试 6 项（合计 416），`scripts/check_repo.py` 契约门禁 34 项 0 警告；
- 轻量部署：无容器编排依赖，Debian 12 / Ubuntu 22.04+ 一台 2 核 4G 主机即可运行，nginx 单端口统一入口（公网只开 80）。

## 系统架构

```mermaid
graph LR
    BR["浏览器（零构建单页看板 web/index.html）"]
    NG["nginx 统一入口（:80，deploy/nginx.conf）"]
    A["A 设备资产与运行监测（:8101）"]
    B["B 故障预警与健康评估（:8102）"]
    C["C 维修工单与备件管理（:8103）"]
    D["D 身份权限与通知集成（:8104）"]

    BR --> NG
    NG -->|"/a"| A
    NG -->|"/b"| B
    NG -->|"/c"| C
    NG -->|"/d"| D
    A -->|"监测样本送评 C-INT-02"| B
    B -->|"高风险预警自动建单 C-INT-03"| C
    C -->|"维修状态事件 C-INT-04"| A
    C -->|"维修结论关闭预警 C-INT-05"| B
    D -.->|"登录 JWT / 权限上下文"| BR
```

四服务同机部署、互调走本机回环（127.0.0.1），各自使用独立 SQLite 数据库；对外推荐 nginx 单端口方案（四服务与看板全部经 80 端口，uvicorn 仅绑 127.0.0.1），亦支持 `LISTEN_HOST=0.0.0.0` 直连多端口模式（调试用）。

## 目录结构

```text
maintenance-work-order-system/
  apps/
    equipment-monitoring/     # A 设备资产与运行监测（:8101）
    fault-warning/            # B 故障预警与健康评估（:8102）
    maintenance/              # C 维修工单与备件管理（:8103）
    integration-quality/      # D 身份权限、通知与集成质量（:8104）
  contracts/
    openapi.yaml              # 机器契约：20 路径 / 24 操作
    shared-enums.json         # 公共枚举：7 roleCode / 21 permissionCode 等
    schemas/                  # 跨模块事件 Schema
    examples/                 # 契约示例报文（契约测试数据源）
    http/                     # local-api.http 联调请求集
  shared/                     # 跨模块公共约定
  tests/                      # 顶层契约示例测试
  web/
    index.html                # 零构建单页看板入口（统一入口 http://127.0.0.1:8888/）
    dashboard.html            # 旧链接兼容重定向 → index.html
  scripts/
    start_all.ps1             # Windows 一键启动四服务 + 8888 统一入口（含 Python/venv/依赖自举）
    start_all.sh              # Debian/Ubuntu 一键启动（幂等，含健康等待与依赖自举）
    dev_server.py             # 本机单端口统一入口：静态 web/ + 反代 /a /b /c /d（跨平台，Windows 用）
    check_repo.py             # 契约与结构门禁（32 项）
    check_commit_msg.py       # 提交信息格式检查（Git hook）
    e2e_demo.py               # 端到端回归演示脚本
    bootstrap.ps1 / bootstrap.sh / configure_team.py  # 四人协作初始化
  deploy/
    nginx.conf                # nginx 单端口统一入口配置
  docs/
    01_模块边界与责任矩阵.md
    06_详细接口约定与联调手册.md
    07_服务器部署说明.md
    工业设备智能运维与预测性维护系统.md   # 业务纲领
    参赛材料/作品说明文档.md              # 大赛六章模板说明文档
    所有流程路线与bug.md                 # 演示剧本与 bug 台账
  AI初步生成的结果/
    IDE提示词/                # 20 余份任务书/提示词（AI 辅助开发全过程证据）
```

## 快速开始

**Windows 本机演示**（PowerShell，需 Python 3.10+ 已加入 PATH）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1
```

脚本首次运行会自动完成自举：检查 Python 版本 → 创建仓库根 `.venv` → 安装四服务依赖 → 生成各服务 `.env`（SQLite 独立数据库、统一内部令牌）→ 启动四服务并轮询 `/health` 直到就绪（最长 60 秒），最后再起一个 **统一入口**（默认端口 `8888`；静态托管 `web/`，并把 `/a /b /c /d` 反代到四服务，与服务器 nginx 同口径）。

> **`.env` 会自检并自愈**：脚本按各服务 `src/config.py` 实际读取的键名校验 `.env`。
> 键名齐全则沿用；缺键（例如早期版本给 B 服务写错键名留下的旧文件）会**先备份**
> （`.env.bak-<时间戳>`）再重生。B 服务的键名与其它三个不同（`DATABASE_URL` /
> `*_SERVICE_URL`），历史病根就在这里：写错后回连地址落回 `localhost`，Windows
> 把 `localhost` 优先解析成 IPv6 `::1`，而服务只监听 `127.0.0.1`，于是身份校验
> 失败、前端显示"登录已过期"并反复登出。现在无论新旧安装都能自动纠正。
>
> **依赖不可达 ≠ 登录过期**：A/B/C 调 D（身份服务）连接失败时返回 **503
> `UPSTREAM_UNAVAILABLE`**（"依赖服务暂时不可用"），只有 D 明确判定令牌无效/过期
> 才返回 401。前端也只把 401 当会话过期，503 不再把用户登出。

然后浏览器打开 **`http://127.0.0.1:8888/`**（即为统一入口，页面默认服务地址 `/a /b /c /d` 可直接用），点击快捷身份一键登录（演示密码 `demo123456`）。

> **8888 被占用**（例如本机跑着 Jupyter）时，脚本会明确报错并**拒绝强杀占用进程**。换个端口即可：
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -WebPort 8889
> # 然后打开 http://127.0.0.1:8889/
> ```
>
> `-Stop` 会自动读回上次启动用的端口；且它只结束命令行含 `uvicorn` / `dev_server.py` 的自己人，不会误杀同端口的其它程序。

> 也可以用浏览器直接打开 `web/index.html`；此时同源反代不可用，脚本会把四个服务地址框自动填成 `http://127.0.0.1:8101~8104` 直连（四个服务已开启跨域）。
> 其它参数：`-SkipInstall` 跳过依赖安装、`-NoWeb` 不启动统一入口。

收尾统一用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -Stop
```

**Linux 服务器**（Debian 12 / Ubuntu 22.04+，python3 ≥ 3.10）：

```bash
bash scripts/start_all.sh          # 一键启动（幂等，可重复执行）
bash scripts/start_all.sh status   # 查看四服务健康状态
bash scripts/start_all.sh stop     # 停止四服务
```

按演示剧本操作：设备详情页"注入异常（严重）" → 设备变红、生成预警、自动创建工单 → 主管确认/派单 → 工程师接单/维修/提交验收 → 验收通过 → 设备恢复运行。完整剧本见 `docs/所有流程路线与bug.md`。

## 测试与契约门禁

```powershell
# 四模块共 410 项测试（A 54 / B 222 / C 98 / D 36）
Push-Location apps\equipment-monitoring;  python -m pytest -q; Pop-Location
Push-Location apps\fault-warning;         python -m pytest -q; Pop-Location
Push-Location apps\maintenance;           python -m pytest -q; Pop-Location
Push-Location apps\integration-quality;   python -m pytest -q; Pop-Location

# 顶层测试（契约示例 + 环境配置一致性）+ 仓库门禁
python -m pytest tests -q
python scripts\check_repo.py      # 34 项校验，0 警告
python scripts\e2e_demo.py        # 端到端回归（需先启动四服务）
```

门禁覆盖：必需文件、OpenAPI 3.1、operationId 唯一、接口契约编号完整、写接口幂等键、公共枚举与 OpenAPI 逐项一致、事件 Schema 示例报文校验等。顶层测试另含**环境配置一致性**回归：启动脚本生成的 `.env` 键名必须能被对应服务 `config.py` 读到、`config`/`.env.example` 不得出现 `localhost`、含中文的 `.ps1` 必须保留 UTF-8 BOM。

## 服务器部署（systemd 托管，阶段4）

单机真实部署（含 nginx 单端口统一入口、SSH 隧道方案、防火墙/安全组清单与 FAQ）见 **`docs/07_服务器部署说明.md`**。当前演示服务器的标准部署流程：

```bash
# 1) nginx 统一入口（8888，模板与线上口径一致）
sudo apt install -y nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ims
sudo ln -s /etc/nginx/sites-available/ims /etc/nginx/sites-enabled/ims
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 2) 四服务 systemd 托管（开机自启 + 崩溃 3s 拉起 + journald 统一日志）
bash deploy/systemd/install.sh

# 3) 验证
bash scripts/start_all.sh status    # 四服务健康
curl http://127.0.0.1:8888/a/health
```

之后浏览器访问 `http://<服务器IP>:8888/`（看板由 nginx 静态托管，默认零配置——服务地址框初始即同源 `/a`~`/d`）。

### 运维速查（systemd 模式）

| 操作 | 命令 |
| --- | --- |
| 状态/日志 | `systemctl status ims-a` · `journalctl -u ims-a -f` |
| 重启某服务 | `systemctl restart ims-b` |
| 演示数据重置 | `echo y \| python scripts/reset_demo.py`（自动经 systemctl 停起） |
| 卸载托管 | `bash deploy/systemd/install.sh --uninstall`（回退 `start_all.sh` nohup 开发模式） |

`scripts/start_all.sh` 与 `reset_demo.py` 会自动感知：装过 systemd 单元走 `systemctl`，未装则保持原 nohup 开发模式，一套入口两种模式。

## 团队分工与协作规范

| 成员 | 负责模块 | 代码目录 | 说明 |
| --- | --- | --- | --- |
| A | 设备资产与运行监测 | `apps/equipment-monitoring/` | 设备档案、遥测、状态 |
| B | 故障预警与健康评估 | `apps/fault-warning/` | 健康评分、风险等级、预警事件 |
| C | 维修工单与备件管理 | `apps/maintenance/` | 工单状态机、备件闭环（项目发起人） |
| D | 系统集成与质量保障 | `apps/integration-quality/`、`tests/` | 身份权限、通知、契约门禁、部署 |

协作方式（据实说明）：A/B/D 模块代码由 **AI 预生成**（湛卢 IDE + 提示词任务书驱动，Git 署名 zh3g）、经人工审查验收后入库；C 模块为项目发起人实现。修改 `contracts/`、`shared/` 等公共资产须受影响成员评审。分支、提交信息、Issue/PR 流程与硬规则见 `README-TEAM.md` 与 `CONTRIBUTING.md`。

## 说明

- 本仓库为 2026 移动云杯 AI Coding 赛道参赛作品，参赛说明文档见 `docs/参赛材料/作品说明文档.md`（六章模板）；
- AI 辅助开发的全过程证据（Wave0 起共 20 余份任务书与提示词）完整保留在 `AI初步生成的结果/IDE提示词/`；
- `.env` 中的内部令牌与 JWT 密钥为演示占位值，仅限演示与彩排使用，生产环境必须替换并收紧（安全建议见 `docs/07` 第六节）。
