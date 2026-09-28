# Wave 4d 任务书：Debian 服务器一键启停脚本（以产品愿景文档为纲）

> 参考文档（产品愿景）：`docs/工业设备智能运维与预测性维护系统.md`
> 关联背景：Windows 版 scripts/start_all.ps1 已验证四服务本机闭环（142 测试绿 +
> E2E 20 断言 + 浏览器看板全流程），本波次做 Linux(Debian) 等价物，目标"整个流程跑在服务器上"。
>
> 前置状态：feat/d-advance-baseline，四服务 + web/dashboard.html 就绪，CORS 已开。

## 目标

交付 `scripts/start_all.sh`：Debian 上自举（venv + 依赖）→ 生成各服务独立 .env →
后台启动四服务（uvicorn **--host 0.0.0.0**）→ 轮询 /health 至全部 UP → `stop` 子命令停止。
另附 `docs/07_服务器部署说明.md` 部署手册（从裸机到看板可用的完整命令序列）。

## 与 Windows 版的差异（必须处理的三点）

1. **绑定地址**：uvicorn 必须绑 `0.0.0.0`（Windows 版是 127.0.0.1，服务器版不改则外网不可达）；
2. **服务间互调地址不变**：.env 里 MEMBER_*_BASE 仍写 `http://127.0.0.1:810x`（四服务同机互调走本机回环）；
3. **自举安装**：脚本首次运行需检查 python3（>=3.10）、创建共享或每服务 venv、pip 安装依赖
   （以各 app 目录 requirements.txt 为准，若无则用根 requirements.txt），幂等可重复执行。

## 端口清单（写进部署手册）

- 8101 A 设备监测 / 8102 B 故障预警 / 8103 C 维修工单 / 8104 D 身份通知（TCP 入站全开）
- 22 SSH 部署管理
- 安全建议：内部令牌为演示占位值，彩排后建议防火墙/安全组限源 IP

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是"工业设备智能运维与预测性维护系统"，
四个 FastAPI 服务（A 设备监测 8101 / B 故障预警 8102 / C 维修工单 8103 / D 身份通知 8104），
Windows 版一键启停在 scripts/start_all.ps1（先精读它，理解 .env 生成逻辑与健康检查流程）。
现在要交付 Linux(Debian) 服务器等价脚本，让整个系统跑在远程服务器上。

你的任务有两个：

一、创建 scripts/start_all.sh（bash，幂等，可重复执行）：
   用法：bash scripts/start_all.sh          # 启动
         bash scripts/start_all.sh stop     # 停止
         bash scripts/start_all.sh status    # 查看四服务健康状态
   要求：
   1. 自举：检查 python3 存在且 >=3.10（没有则报错并提示 apt install 命令）；
      在仓库根创建共享 .venv（幂等），pip install 各服务依赖——先读
      apps/*/requirements.txt 确认实际有哪些依赖清单，缺目录级清单的用根 requirements.txt；
   2. 生成 .env：与 start_all.ps1 的 Get-EnvContent 逐字段一致
      （MEMBER_A_PORT=8101、MEMBER_A_DATABASE_URL=sqlite:///./member_a.db、
       INTERNAL_API_TOKEN=dev-internal-token-change-me、MEMBER_B/C/D_BASE=http://127.0.0.1:810x，
       B/C/D 同理，变量名以各 app src/config.py 为准，先读它们核对）；
      已存在则沿用不覆盖；
   3. 启动：每服务一个后台进程，工作目录为其 app 目录，
      .venv 的 uvicorn src.main:app --host 0.0.0.0 --port <端口>，
      stdout/stderr 重定向到 logs/<code>.log（自动建 logs/，git 忽略），
      PID 写 .run/<code>.pid（自动建 .run/，git 忽略，.gitignore 已有规则则不重复加）；
   4. 健康检查：轮询 http://127.0.0.1:<port>/health 至四服务全部 status=UP（60s 超时），
      超时则列出未就绪服务与其日志尾部 20 行后 exit 1；
   5. stop：按 .run/*.pid 逐个 kill，pid 文件失效（进程已死）则按端口兜底
      （ss -ltnp 或 fuser），最后清理 .run/；
   6. status：逐服务 curl /health 打印 UP/DOWN 与响应 JSON。
   风格：set -euo pipefail；中文输出与 ps1 版式一致（[ENV ]/[RUN ]/[OK  ] 前缀）。

二、创建 docs/07_服务器部署说明.md（部署手册）：
   从裸机 Debian 到浏览器可用看板的完整命令序列：
   apt 安装 python3/venv/git → git clone → bash scripts/start_all.sh →
   验证 curl 各 /health → 本地打开 web/dashboard.html 并把四个服务地址框
   从 127.0.0.1 改为服务器 IP → 登录演示（USER-D-001 / demo123456）。
   附端口清单表（8101-8104 TCP 入站 + 22 SSH）与安全建议
   （演示占位令牌、彩排后限源 IP）、SSH 隧道替代方案
   （ssh -L 8101:localhost:8101 ... -L 8104:localhost:8104，免开公网端口）。

完成后必须实际验证并贴输出：
1. bash -n scripts/start_all.sh（语法检查）；
2. 若有 shellcheck 则跑 shellcheck scripts/start_all.sh；
3. 实跑验证（二选一，如实标注用的哪种）：
   a) 在 WSL Ubuntu 中：cd 到仓库（或拷贝），bash scripts/start_all.sh 启动，
      curl 四个 /health 全 UP，bash scripts/start_all.sh stop 后端口全释放；
   b) 无 WSL 则说明无法实跑，仅交语法检查 + 逐行自审清单（.env 变量名与 config.py 对照表）。
4. 确认 .gitignore 覆盖 logs/ 与 .run/（没有则补）。

约束：
- 允许改动：新增 scripts/start_all.sh、docs/07_服务器部署说明.md、
  .gitignore（仅补 logs/ 与 .run/ 两行，如缺）、本任务书使用记录；
- 禁止改动：任何 src/、contracts/、tests/、web/、start_all.ps1；
- 不得引入 docker/systemd 等新依赖（保持裸 bash + venv，比赛演示环境越简单越稳）。
完成后在本任务书末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. `bash -n` 语法过 + 我在 WSL Ubuntu 实跑：四服务全 UP（/health 200）、stop 后端口释放；
2. `.env` 生成内容与 ps1 版逐字段一致（变量名对照各 config.py 核对）；
3. uvicorn 绑定 0.0.0.0（`ss -ltn` 验证四端口监听 0.0.0.0 而非 127.0.0.1）;
4. WSL 里跑 python scripts/e2e_demo.py（或等价冒烟）无回归；
5. 改动范围 diff 核对：仅 start_all.sh + docs/07 + .gitignore 两行 + 任务书。

## 使用记录

- 2026-09-28 · 湛卢 IDE · 任务：交付 `scripts/start_all.sh`（约 300 行，bash，`set -euo pipefail`，幂等）+ `docs/07_服务器部署说明.md` + `.gitignore` 补 `logs/`、`.run/` 两行。
  - **start**：python3 检查（>=3.10，缺失/过低给 apt 提示）→ 仓库根共享 `.venv`（幂等）→ 按四份 `apps/*/requirements.txt` 装依赖（逐份提示 [DEPS]，pip 失败给清华镜像提示）→ `.env` 生成与 ps1 版 Get-EnvContent **逐字段一致**（含 C 服务 `DATABASE_URL` 特例，已对照四份 src/config.py 核对；已存在沿用）→ 每服务后台 uvicorn **--host 0.0.0.0**（工作目录=app 目录），日志 `logs/<代号>.log`、PID `.run/<代号>.pid` → 轮询 /health 至全部 UP（60s 超时贴未就绪服务日志尾 20 行 exit 1）；单服务进程提前退出也会即时贴日志退出。已在运行的服务 [SKIP] 跳过（幂等）。
  - **stop**：按 `.run/*.pid` 逐个 TERM（最多等 2s 后 KILL）；PID 记录失效或端口仍被占则按端口兜底（`ss -ltnp` 提取 pid，同一等待语义），最后清理 `.run/`。
  - **status**：逐服务 curl /health 打印 [UP]/[DOWN] 与响应 JSON，全 UP 退出码 0。
  - **验证**（在 Windows 开发机上以 **WSL Ubuntu-22.04.5（Python 3.10.12）实跑**，仓库拷贝至 WSL 本地并清空 .env/*.db 走全新自举）：
    - `bash -n` 通过；`shellcheck`（WSL root apt 安装 0.8.0）**0 问题**（首轮报 SC2034/SC2015 两处已修）；
    - 首次启动：venv 创建 + 4×[DEPS] + 4×[ENV ] 新建 + 4×[RUN] + 4×[OK ] UP；
    - `ss -ltn` 四端口全部监听 **0.0.0.0:810x**；`.run` PID 与 `ss -ltnp` 实际监听进程**完全一致**；
    - `.venv/bin/python scripts/e2e_demo.py` **20 断言全过**（1.33s，Linux 环境无回归）；
    - 二次 start：4×[SKIP]（幂等）+ 全 UP；stop：4×"PID xx 已终止"+ 端口全部释放终检通过；
    - WSL 生成的四个 .env 与 ps1 版逐字段一致（cat 全文对照）。
  - **实跑抓出并修复的 3 处缺陷**（bash -n/shellcheck 均不报，实跑价值）：
    1. `install_deps`/`ensure_envs` 的 `IFS='|' read` 只给 3 个变量名（漏 port），第 4 字段并入目录名导致 cd 失败——补 `port`；
    2. `( cd dir && nohup uvicorn & echo $! )` 中 `A && B &` 整体为后台任务，`$!` 是中间 shell 而非 uvicorn 本体（实测 $!=3617、实际=3618），PID 主路径失效、二次 start 不 SKIP——改为 `pushd` + 直接 `nohup ... &`（实测 $!=PID=监听进程）；
    3. 兜底 kill 后立即查端口导致 TERM 优雅退出期误报"仍有监听"——兜底路径补齐与主路径一致的 TERM→等 2s→KILL 等待语义。
  - **改动范围**：仅新增 `scripts/start_all.sh`、`docs/07_服务器部署说明.md`、`.gitignore` +2 行（`git check-ignore` 验证生效）、本使用记录；未动任何 src/、contracts/、tests/、web/、start_all.ps1。验证用 WSL 拷贝件 ~/ims4d 保留可复验，未影响仓库。
