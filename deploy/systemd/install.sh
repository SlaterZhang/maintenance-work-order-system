#!/usr/bin/env bash
# 安装四服务 systemd 单元（阶段4部署规范化，2026-10-06）。
#
# 在仓库根执行：
#   bash deploy/systemd/install.sh            # 安装 + enable --now
#   bash deploy/systemd/install.sh --uninstall # 停用并移除单元
#
# 单元特性：开机自启、崩溃 3 秒自动拉起、日志统一 journald
# （journalctl -u ims-a -f）。仓库路径按本脚本位置自动注入，
# 换服务器/换目录重装即可。
set -euo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TPL_DIR="$REPO/deploy/systemd"
UNIT_DIR="/etc/systemd/system"
UNITS=(ims-a ims-b ims-c ims-d)

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root（写 $UNIT_DIR）。请用 sudo 执行。" >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  echo "== 停用并移除 systemd 单元 =="
  systemctl disable --now "${UNITS[@]}" 2>/dev/null || true
  rm -f "$UNIT_DIR"/ims-{a,b,c,d}.service
  systemctl daemon-reload
  echo "已移除。之后可用 bash scripts/start_all.sh 以开发模式（nohup）启动。"
  exit 0
fi

echo "== 安装 systemd 单元（仓库：$REPO） =="
for u in "${UNITS[@]}"; do
  sed "s|@REPO@|$REPO|g" "$TPL_DIR/$u.service.template" > "$UNIT_DIR/$u.service"
  echo "  已生成 $UNIT_DIR/$u.service"
done
systemctl daemon-reload
systemctl enable --now "${UNITS[@]}"
sleep 2
systemctl --no-pager --lines=0 status "${UNITS[@]}" | grep -E "ims-|Active:" || true
echo
echo "完成：四服务已 systemd 托管（开机自启 + 崩溃拉起）。"
echo "  状态：systemctl status ims-a ims-b ims-c ims-d"
echo "  日志：journalctl -u ims-a -f   （或 -u 'ims-*'）"
echo "  重启：systemctl restart ims-a"
echo "  scripts/start_all.sh 与 reset_demo.py 已自动感知 systemd 模式。"
