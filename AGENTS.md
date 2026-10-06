# AGENTS.md - 项目开发规范

## 开发流程

### 1. 本地开发 → 服务器同步
- 所有功能修改在本地 Windows 电脑进行
- 每次关键更改用 git 存档（commit）
- 主动同步到服务器（git push + 服务器 git pull）

### 2. 任务执行规范
- AI 给出可行方案，交给 zl（智谱AI IDE）修改代码
- AI 验收通过后，用 git commit 提交

### 3. 同步步骤
```bash
# 本地提交
git add .
git commit -m "feat: 描述功能"

# 推送到远程
git push origin feat/d-advance-baseline

# 服务器拉取
cd /root/maintenance-work-order-system
git pull origin feat/d-advance-baseline --rebase
```

## 技术栈

- 前端：HTML + CSS + JavaScript（看板 `web/index.html` + `web/css/` + `web/js/`，零构建）
- 后端：Python FastAPI（4个微服务）
- 端口：8101(A) / 8102(B) / 8103(C) / 8104(D)
- 入口：8888（nginx）→ /a /b /c /d 路径代理
- 服务托管：systemd（`ims-a/b/c/d.service`，`deploy/systemd/install.sh` 安装；`start_all.sh`/`reset_demo.py` 自动感知两种模式）

## 硬约定（阶段4增补，2026-10-06）

1. **改数据库模型必须过迁移脚本**：任何 SQLAlchemy 模型（`apps/*/src/domain/models.py`）的字段增删改，禁止只改代码不提供存量数据升级路径。演示库生命周期允许"清库重建"（`reset_demo.py` 备份后重建），因此新增列时必须同时确认：(a) `reset_demo.py` 重建路径已覆盖新列；(b) 若存在无法重建的环境，须补迁移脚本（如 `scripts/migrate_*.py`）并在提交说明中写明；
2. **systemd 托管环境的服务操作**：演示服务器已装 `ims-a/b/c/d.service`，重启服务一律走 `systemctl restart ims-<x>` 或 `bash scripts/start_all.sh stop && bash scripts/start_all.sh`（脚本会自动转发到 systemctl）；改代码后必须重启对应服务才生效；
3. **nginx 口径**：线上配置 `/etc/nginx/sites-available/ims` 与 `deploy/nginx.conf` 保持同步（端口 8888、root 指向仓库 `web/`），改入口配置须两处同改；
4. **新增前端静态文件**：`web/` 下用工具创建的文件权限常为 600，nginx 读取会 403——发布前 `chmod 644` 该文件。

## 约定

- 分支：feat/d-advance-baseline
- 远程仓库：git@github.com:SlaterZhang/maintenance-work-order-system.git
- 服务器：root@36.213.152.237，项目路径 /root/maintenance-work-order-system