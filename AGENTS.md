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

- 前端：HTML + JavaScript（看板 dashboard.html）
- 后端：Python FastAPI（4个微服务）
- 端口：8101(A) / 8102(B) / 8103(C) / 8104(D)
- 入口：8888（nginx）→ /a /b /c /d 路径代理

## 约定

- 分支：feat/d-advance-baseline
- 远程仓库：git@github.com:SlaterZhang/maintenance-work-order-system.git
- 服务器：root@36.213.152.237，项目路径 /root/maintenance-work-order-system