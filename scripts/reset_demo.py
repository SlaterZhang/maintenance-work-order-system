#!/usr/bin/env python3
"""演示数据重置：停服 → 备份 → 清库 → 重启 → 种子自检。

把四个 SQLite 数据库恢复到干净的种子状态（A：3 台设备；D：7 个身份；
B/C：无预警无工单），用于演示前重置现场或修复后恢复基线。

背景：``create_all`` 只建表不改表，代码模型演进后存量库会脱节
（2026-10-06 的 health_evaluation.response_body NOT NULL 500 即由此而来）。
本脚本按"清库重建"策略彻底消除新旧结构混装。

用法：
    .venv/bin/python scripts/reset_demo.py          # 交互确认
    .venv/bin/python scripts/reset_demo.py --yes    # 跳过确认（脚本/CI 用）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# code | 服务目录 | 端口 | 数据库文件（相对各服务目录）
SERVICES = [
    ("A", "apps/equipment-monitoring", 8101, "member_a.db"),
    ("B", "apps/fault-warning", 8102, "member_b.db"),
    ("C", "apps/maintenance", 8103, "member_c.db"),
    ("D", "apps/integration-quality", 8104, "member_d.db"),
]

SEED_USERNAMES = [
    "USER-A-001", "USER-C-002", "USER-C-003", "USER-D-001",
    "USER-B-001", "USER-C-001", "USER-C-004",
]
DEMO_PASSWORD = "demo123456"


def http_json(method: str, url: str, body: dict | None = None,
              headers: dict | None = None, timeout: float = 5.0):
    """最小 JSON 请求工具（只依赖标准库），返回 (status, data)。"""
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"}
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, (json.loads(raw) if raw else None)
        except json.JSONDecodeError:
            return e.code, None


def run_start_all(*args: str) -> bool:
    cmd = ["bash", str(REPO_ROOT / "scripts" / "start_all.sh"), *args]
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=REPO_ROOT, timeout=240,
                          capture_output=True, text=True)
    print(proc.stdout.rstrip())
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), file=sys.stderr)
    return proc.returncode == 0


def stop_services() -> bool:
    print("== 停止四服务 ==")
    return run_start_all("stop")


def backup_and_clean() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = REPO_ROOT / "backups" / f"reset-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("== 备份并清空数据库 ==")
    for code, rel_dir, _port, db_name in SERVICES:
        db_path = REPO_ROOT / rel_dir / db_name
        if db_path.exists():
            shutil.copy2(db_path, backup_dir / db_name)
            print(f"  [{code}] 备份 {rel_dir}/{db_name} → {backup_dir.name}/")
        for sidecar in (str(db_path) + "-wal", str(db_path) + "-shm"):
            Path(sidecar).unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
    return backup_dir


def start_services() -> bool:
    print("== 重新启动四服务（按当前模型重建库并种子） ==")
    return run_start_all("start")


def wait_health(timeout: float = 60.0) -> bool:
    print("== 等待 /health 全部 UP ==")
    deadline = time.time() + timeout
    pending = {code: port for code, _d, port, _b in SERVICES}
    while pending and time.time() < deadline:
        for code, port in list(pending.items()):
            status, _ = http_json("GET", f"http://127.0.0.1:{port}/health")
            if status == 200:
                print(f"  [{code}] 端口 {port} UP")
                del pending[code]
        if pending:
            time.sleep(2)
    return not pending


def self_check() -> bool:
    print("== 种子态自检 ==")
    ok = True
    checks: list[tuple[str, bool, str]] = []

    # D 登录取 JWT（阶段1鉴权闭合后用户态查询一律 Bearer）
    tokens: dict[str, str] = {}
    for uid in SEED_USERNAMES:
        status, data = http_json(
            "POST", "http://127.0.0.1:8104/api/v1/auth/login",
            body={"username": uid, "password": DEMO_PASSWORD})
        if status == 200 and (data or {}).get("accessToken"):
            tokens[uid] = data["accessToken"]
    checks.append(("D 7 个身份可登录", len(tokens) == len(SEED_USERNAMES),
                   f"{len(tokens)}/{len(SEED_USERNAMES)} 取得令牌"))

    def bearer(uid: str) -> dict:
        return {"Authorization": f"Bearer {tokens[uid]}",
                "X-Trace-Id": "trace-reset-check"}

    # A：3 台设备
    status, data = http_json(
        "GET", "http://127.0.0.1:8101/api/v1/equipment?pageSize=100")
    n = (data or {}).get("total") if status == 200 else None
    checks.append(("A 设备数 = 3", n == 3, f"实际 {n}"))

    # B：无预警（预警分析员身份，WARNING_READ）
    status, data = http_json(
        "GET", "http://127.0.0.1:8102/api/v1/warnings?pageSize=1",
        headers=bearer("USER-B-001"))
    n = (data or {}).get("total") if status == 200 else None
    checks.append(("B 预警数 = 0", status == 200 and n == 0,
                   f"HTTP {status}, total={n}"))

    # B：latest 接口（登录身份即可）为空评估
    status, data = http_json(
        "GET", "http://127.0.0.1:8102/api/v1/health-evaluations/latest?equipmentId=EQ-000001",
        headers=bearer("USER-A-001"))
    has = (data or {}).get("hasEvaluation")
    checks.append(("B latest 空评估 + 无需内部令牌",
                   status == 200 and has is False,
                   f"HTTP {status}, hasEvaluation={has}"))

    # C：无工单（登录身份即可）
    status, data = http_json(
        "GET", "http://127.0.0.1:8103/api/v1/work-orders?pageSize=1",
        headers=bearer("USER-C-001"))
    n = (data or {}).get("total") if status == 200 else None
    checks.append(("C 工单数 = 0", status == 200 and n == 0,
                   f"HTTP {status}, total={n}"))

    for label, passed, detail in checks:
        mark = "√" if passed else "×"
        print(f"  [{mark}] {label}（{detail}）")
        ok = ok and passed
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="重置演示数据到干净种子态")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    args = parser.parse_args()

    if not args.yes:
        answer = input("将停止四服务并清空全部业务数据（自动备份到 backups/），"
                       "确认继续？(y/N) ").strip().lower()
        if answer != "y":
            print("已取消。")
            return 1

    if not stop_services():
        print("停止服务失败，中止（可手动检查：ss -tlnp | grep -E '810[1-4]'）",
              file=sys.stderr)
        return 1
    backup_dir = backup_and_clean()
    if not start_services():
        print("启动服务失败，中止（查看 logs/A.log ~ logs/D.log）", file=sys.stderr)
        return 1
    if not wait_health():
        print("健康检查超时，中止", file=sys.stderr)
        return 1
    if not self_check():
        print(f"\n自检未全部通过。数据库已备份在 {backup_dir}", file=sys.stderr)
        return 1

    print(f"\n重置完成：四服务已按当前代码模型重建种子数据。")
    print(f"  备份位置：{backup_dir}")
    print(f"  恢复方式：停服后把备份目录中的 .db 拷回各服务目录再启动")
    print(f"  演示入口：http://<服务器IP>:8888/  （快捷身份密码 {DEMO_PASSWORD}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
