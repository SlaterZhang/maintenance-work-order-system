#!/usr/bin/env bash
# Wave 4d 四服务一键启动 / 停止 / 状态（Debian 服务器版，scripts/start_all.ps1 的 Linux 等价物）
# A 设备监测(8101) / B 故障预警(8102) / C 维修工单(8103) / D 身份通知(8104)
# 首次运行自举：检查 python3(>=3.10) → 创建仓库根共享 .venv → pip 安装各服务依赖
# → 生成各服务独立 .env → 后台启动 uvicorn（绑定地址由 LISTEN_HOST 控制）→ 轮询 /health 至全部 UP。
# 用法：
#   bash scripts/start_all.sh          # 启动（默认子命令，可省略）
#   bash scripts/start_all.sh stop     # 停止四服务并清理 PID 记录
#   bash scripts/start_all.sh status   # 查看四服务健康状态
set -euo pipefail

# ---------- 常量 ----------
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
LOGS_DIR="$REPO_ROOT/logs"
RUN_DIR="$REPO_ROOT/.run"

# uvicorn 绑定地址（两种模式）：
#   默认 127.0.0.1（nginx 单端口方案在前的推荐值）：仅本机回环 + nginx 反代，公网不可直连
#   export LISTEN_HOST=0.0.0.0：恢复 Wave4d 直连模式（8101~8104 对外可达，兼容旧用法与直接测试）
LISTEN_HOST="${LISTEN_HOST:-127.0.0.1}"

# 四服务：代号|标题|目录|端口（与 start_all.ps1 一致）
SERVICES=(
  "A|设备监测|apps/equipment-monitoring|8101"
  "B|故障预警|apps/fault-warning|8102"
  "C|维修工单|apps/maintenance|8103"
  "D|身份通知|apps/integration-quality|8104"
)

# ---------- 输出（中文 + 与 ps1 版式一致的前缀） ----------
if [ -t 1 ]; then
  C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_OFF=""
fi
info() { printf '%s\n' "${C_CYAN}$*${C_OFF}"; }
ok()   { printf '%s\n' "${C_GREEN}$*${C_OFF}"; }
warn() { printf '%s\n' "${C_YELLOW}$*${C_OFF}"; }
err()  { printf '%s\n' "${C_RED}$*${C_OFF}" >&2; }

# ---------- 小工具 ----------
# port_pids <port> ：列出监听该端口的进程 PID（依赖 iproute2 的 ss，Debian/Ubuntu 默认自带）
port_pids() {
  ss -ltnp 2>/dev/null | awk -v p=":$1\$" '$4 ~ p' \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u
}
port_listening() { [ -n "$(port_pids "$1")" ]; }

health_body() {  # curl /health 响应体，失败输出空串
  curl -fsS --max-time 3 "http://127.0.0.1:$1/health" 2>/dev/null || true
}
is_up() {  # 判断响应体是否 status=UP
  printf '%s' "${1:-}" | grep -q '"status"[[:space:]]*:[[:space:]]*"UP"'
}

# systemd 托管检测（阶段4）：装过 deploy/systemd 单元就走 systemctl，
# 没装则回退本脚本自带的 nohup 开发模式——一个入口两种模式。
systemd_managed() {
  command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files ims-a.service --no-legend 2>/dev/null | grep -q .
}

# ---------- 1. 自举：python3 检查 ----------
check_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "未找到 python3。请先安装：sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
  fi
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    err "python3 版本过低（需 >= 3.10，当前 $(python3 -V 2>&1 || echo 未知)）。"
    err "请升级：sudo apt update && sudo apt install -y python3 python3-venv"
    exit 1
  fi
}

# ---------- 2. 自举：共享 venv（幂等） ----------
ensure_venv() {
  if [ -x "$VENV_DIR/bin/python" ]; then
    info "[VENV] 已存在，沿用 $VENV_DIR"
    return
  fi
  info "== 创建共享虚拟环境（仓库根 .venv，幂等） =="
  if ! python3 -m venv "$VENV_DIR"; then
    err "venv 创建失败。Debian 通常缺少 python3-venv，请执行："
    err "  sudo apt update && sudo apt install -y python3-venv"
    exit 1
  fi
}

# ---------- 3. 自举：安装四服务依赖（幂等，以各 app 目录 requirements.txt 为准） ----------
install_deps() {
  info "== 安装四服务依赖（首次较慢，幂等可重复执行） =="
  local S code title dir port
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    if ! ( cd "$REPO_ROOT/$dir" && "$VENV_DIR/bin/pip" install -q --disable-pip-version-check -r requirements.txt ); then
      err "$code-$title 依赖安装失败（$dir/requirements.txt）。"
      err "国内网络可尝试使用镜像源重跑本脚本："
      err "  bash scripts/start_all.sh  # 已装好的依赖不会重复安装"
      err "（手动等价命令：.venv/bin/pip install -r $dir/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple）"
      exit 1
    fi
    ok "[DEPS] $code-$title 依赖就绪（$dir/requirements.txt）"
  done
}

# ---------- 4. 生成各服务 .env（与 start_all.ps1 Get-EnvContent 逐字段一致；已存在沿用不覆盖） ----------
env_content() {
  case "$1" in
    A) cat <<'EOF'
MEMBER_A_PORT=8101
MEMBER_A_DATABASE_URL=sqlite:///./member_a.db
INTERNAL_API_TOKEN=dev-internal-token-change-me
MEMBER_B_BASE=http://127.0.0.1:8102
MEMBER_C_BASE=http://127.0.0.1:8103
MEMBER_D_BASE=http://127.0.0.1:8104
EOF
      ;;
    B) cat <<'EOF'
MEMBER_B_PORT=8102
DATABASE_URL=sqlite:///./member_b.db
INTERNAL_API_TOKEN=dev-internal-token-change-me
EQUIPMENT_SERVICE_URL=http://127.0.0.1:8101
MAINTENANCE_SERVICE_URL=http://127.0.0.1:8103
INTEGRATION_SERVICE_URL=http://127.0.0.1:8104
ALLOW_CLIENT_MOCK=false
EOF
      ;;
    C) cat <<'EOF'
MEMBER_C_PORT=8103
DATABASE_URL=sqlite:///./member_c.db
INTERNAL_API_TOKEN=dev-internal-token-change-me
MEMBER_A_BASE=http://127.0.0.1:8101
MEMBER_B_BASE=http://127.0.0.1:8102
MEMBER_D_BASE=http://127.0.0.1:8104
EOF
      ;;
    D) cat <<'EOF'
MEMBER_D_PORT=8104
MEMBER_D_DATABASE_URL=sqlite:///./member_d.db
INTERNAL_API_TOKEN=dev-internal-token-change-me
MEMBER_A_BASE=http://127.0.0.1:8101
MEMBER_B_BASE=http://127.0.0.1:8102
MEMBER_C_BASE=http://127.0.0.1:8103
EOF
      ;;
  esac
}
ensure_envs() {
  info "== 生成各服务 .env（若不存在，独立数据库互不共用） =="
  local S code title dir port env_path
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    env_path="$REPO_ROOT/$dir/.env"
    if [ -f "$env_path" ]; then
      warn "[ENV ] 已存在，沿用 $env_path"
    else
      env_content "$code" > "$env_path"
      warn "[ENV ] 新建 $env_path"
    fi
  done
}

# ---------- 5. 启动 ----------
do_start() {
  check_python
  ensure_venv
  install_deps
  ensure_envs
  mkdir -p "$LOGS_DIR" "$RUN_DIR"

  # 阶段4：systemd 托管模式（install.sh 装过单元）——重启/开机自启/崩溃拉起交给 systemd
  if systemd_managed; then
    info "== systemd 模式：systemctl start ims-a ims-b ims-c ims-d =="
    if ! systemctl start ims-a ims-b ims-c ims-d; then
      err "systemctl start 失败，查看：journalctl -u ims-a -n 30"
      exit 1
    fi
    info "== 等待 /health 全部 UP（最长 60s） =="
    wait_health_systemd
    echo
    ok "四服务全部 UP（systemd 托管：开机自启 + 崩溃 3s 自动拉起）"
    for S in "${SERVICES[@]}"; do
      IFS='|' read -r code title dir port <<<"$S"
      ok "  $code $title -> $(health_body "$port")"
    done
    echo
    info "停止命令：bash scripts/start_all.sh stop（systemctl stop）· 日志：journalctl -u ims-a -f"
    return
  fi

  info "== 启动四个服务（后台进程，日志在 logs/，PID 在 .run/） =="
  local S code title dir port app_dir pid_file log_file pid
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    app_dir="$REPO_ROOT/$dir"
    pid_file="$RUN_DIR/$code.pid"
    log_file="$LOGS_DIR/$code.log"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
      warn "[SKIP] $code-$title 已在运行（PID $(cat "$pid_file")），跳过"
      continue
    fi
    (
      pushd "$app_dir" >/dev/null
      nohup "$VENV_DIR/bin/uvicorn" src.main:app --host "$LISTEN_HOST" --port "$port" \
        >>"$log_file" 2>&1 &
      echo $! > "$pid_file"
      popd >/dev/null
    )
    ok "[RUN ] $code-$title 窗口 PID $(cat "$pid_file") 端口 $port（绑定 $LISTEN_HOST，日志 logs/$code.log）"
  done

  info "== 等待 /health 全部 UP（最长 60s） =="
  wait_health
  echo
  ok "四服务全部 UP："
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    ok "  $code $title -> $(health_body "$port")"
  done
  echo
  info "停止命令：bash scripts/start_all.sh stop"
}

# 健康轮询（systemd 模式）：进程存活由 systemd 保证，这里只等 /health
wait_health_systemd() {
  local deadline=$((SECONDS + 60))
  local -a pending=("${SERVICES[@]}")
  local S code title dir port body
  while [ "${#pending[@]}" -gt 0 ] && [ "$SECONDS" -lt "$deadline" ]; do
    local -a next=()
    for S in "${pending[@]}"; do
      IFS='|' read -r code title dir port <<<"$S"
      body="$(health_body "$port")"
      if is_up "$body"; then
        ok "[OK  ] $code-$title (端口 $port) UP"
      else
        next+=("$S")
      fi
    done
    pending=("${next[@]}")
    [ "${#pending[@]}" -gt 0 ] && sleep 2
  done
  if [ "${#pending[@]}" -gt 0 ]; then
    err "启动失败（60s 超时），以下服务未就绪，最近日志："
    for S in "${pending[@]}"; do
      IFS='|' read -r code title dir port <<<"$S"
      err "  - $code-$title 端口 $port：journalctl -u ims-$code -n 30"
      journalctl -u "ims-$code" -n 30 --no-pager 2>/dev/null || true
    done
    exit 1
  fi
}

# 健康轮询：至四服务全部 UP；单服务进程退出或 60s 超时则贴日志尾部 20 行后 exit 1
wait_health() {
  local deadline=$((SECONDS + 60))
  local -a pending=("${SERVICES[@]}")
  local S code title dir port pid_file log_file body
  while [ "${#pending[@]}" -gt 0 ] && [ "$SECONDS" -lt "$deadline" ]; do
    local -a next=()
    for S in "${pending[@]}"; do
      IFS='|' read -r code title dir port <<<"$S"
      pid_file="$RUN_DIR/$code.pid"
      log_file="$LOGS_DIR/$code.log"
      body="$(health_body "$port")"
      if is_up "$body"; then
        ok "[OK  ] $code-$title (端口 $port) UP"
      elif [ -f "$pid_file" ] && ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        err "[FAIL] $code-$title 进程已退出（端口 $port），日志尾部 20 行："
        tail -n 20 "$log_file" >&2 2>/dev/null || err "（日志 $log_file 不存在）"
        exit 1
      else
        next+=("$S")
      fi
    done
    pending=("${next[@]}")
    [ "${#pending[@]}" -gt 0 ] && sleep 2
  done
  if [ "${#pending[@]}" -gt 0 ]; then
    err "启动失败（60s 超时），以下服务未就绪："
    for S in "${pending[@]}"; do
      IFS='|' read -r code title dir port <<<"$S"
      err "  - $code-$title 端口 $port（http://127.0.0.1:$port/health），日志尾部 20 行："
      tail -n 20 "$LOGS_DIR/$code.log" >&2 2>/dev/null || true
    done
    exit 1
  fi
}

# ---------- 6. 停止 ----------
# term_pid <pid>：TERM 后最多等 2s，仍存活则 KILL；兜底路径复用同一等待语义
term_pid() {
  kill "$1" 2>/dev/null || true
  local _i
  for _i in 1 2 3 4; do
    kill -0 "$1" 2>/dev/null || return 0
    sleep 0.5
  done
  if kill -0 "$1" 2>/dev/null; then
    kill -9 "$1" 2>/dev/null || true
  fi
}
do_stop() {
  info "== 停止四服务 =="
  # 阶段4：systemd 托管模式
  if systemd_managed; then
    systemctl stop ims-a ims-b ims-c ims-d
    ok "[STOP] systemctl stop ims-a ims-b ims-c ims-d 完成"
    return
  fi
  local S code title dir port pid_file pid killed _bp
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    pid_file="$RUN_DIR/$code.pid"
    killed=0
    if [ -f "$pid_file" ]; then
      pid="$(cat "$pid_file" 2>/dev/null || true)"
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        term_pid "$pid"
        ok "[STOP] $code-$title 端口 $port 进程 PID $pid 已终止"
        killed=1
      else
        warn "[STOP] $code-$title PID 记录失效（PID ${pid:-空}），尝试按端口兜底"
      fi
    fi
    # 兜底：pid 记录缺失/失效、或 kill 后端口仍被占
    for _bp in $(port_pids "$port"); do
      term_pid "$_bp"
      ok "[STOP] $code-$title 端口 $port 兜底终止进程 PID $_bp"
      killed=1
    done
    if [ "$killed" -eq 0 ]; then
      warn "[STOP] $code-$title 端口 $port 无监听进程"
    elif port_listening "$port"; then
      err "[STOP] 警告：$code-$title 端口 $port 仍有进程监听（可能是外部程序占用）"
    fi
  done
  rm -f "$RUN_DIR"/*.pid 2>/dev/null || true
  rmdir "$RUN_DIR" 2>/dev/null || true
  info "[STOP] 已清理 PID 记录（$RUN_DIR）"
}

# ---------- 7. 状态 ----------
do_status() {
  info "== 四服务健康状态 =="
  local S code title dir port body down=0
  for S in "${SERVICES[@]}"; do
    IFS='|' read -r code title dir port <<<"$S"
    body="$(health_body "$port")"
    if is_up "$body"; then
      ok "[UP  ] $code-$title (端口 $port) $body"
    else
      err "[DOWN] $code-$title (端口 $port) 无响应或未就绪（http://127.0.0.1:$port/health）"
      down=1
    fi
  done
  if [ "$down" -eq 0 ]; then
    ok "四服务全部 UP"
  else
    err "存在未就绪服务"
  fi
  exit "$down"
}

# ---------- 入口 ----------
usage() {
  cat <<'EOF'
用法：bash scripts/start_all.sh [start|stop|status]
  start    启动四服务并等待全部 UP（默认，可省略）
  stop     停止四服务并清理 PID 记录
  status   查看四服务健康状态
EOF
}
case "${1:-start}" in
  start) do_start ;;
  stop)  do_stop ;;
  status) do_status ;;
  *)     usage; exit 1 ;;
esac
