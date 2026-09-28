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
