"""环境配置一致性回归（2026-10-08 Windows 登录故障后新增）。

背景
----
Windows 上一键脚本把 B 服务的 ``.env`` 写成了 ``MEMBER_B_DATABASE_URL`` /
``MEMBER_A_BASE`` 等键名，而 B 的 ``config.py`` 实际读的是 ``DATABASE_URL`` /
``EQUIPMENT_SERVICE_URL``。pydantic ``extra="ignore"`` 让多余键静默丢弃，
缺失键回落到 ``config.py`` 默认值，于是「碰巧能跑」——直到默认值在 Windows
上解析出 IPv6 ``::1`` 使身份校验连接失败，用户被反复踢下线。

本测试锁住三件事，防止同类问题再次静默发生：
1. 启动脚本生成的每个 ``.env`` 键名，都能被对应服务的 ``config.py`` 读到；
2. ``config.py`` 与 ``.env.example`` 里不再出现 ``localhost``（Windows 会
   优先解析 IPv6，而服务只监听 IPv4）；
3. 四个服务的端口/数据库互不共用（各服务独立库）。
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# 服务 → 目录（与 scripts/start_all.* 的 SERVICES 一致）
SERVICES = {
    "A": "apps/equipment-monitoring",
    "B": "apps/fault-warning",
    "C": "apps/maintenance",
    "D": "apps/integration-quality",
}


def _config_fields(service_dir: str) -> set[str]:
    """解析 app 的 ``Settings`` 字段名（类体里 ``name: type = ...``）。"""
    tree = ast.parse((ROOT / service_dir / "src" / "config.py").read_text(encoding="utf-8"))
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
    return fields


def _env_keys(text: str) -> set[str]:
    return set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=", text, re.M))


def _extract_env_content_blocks(script_text: str) -> dict[str, str]:
    """从启动脚本里抓取每个服务 ``.env`` 的内容块。

    支持两种写法：bash heredoc（``cat <<'EOF' ... EOF``）与 PowerShell
    字符串拼接（``"KEY=value`n"``）。
    """
    blocks: dict[str, str] = {}
    # bash：case "$1" in B) cat <<'EOF' ... EOF ;;
    for match in re.finditer(
        r'(\w)\)\s*cat <<\'EOF\'\n(.*?)\nEOF', script_text, re.S
    ):
        blocks[match.group(1)] = match.group(2)
    # PowerShell：switch ($Code) { "B" { ... } }
    # 键可能出现在开头（"KEY=），也可能被 `n 续接（"A=1`nB=2`n"）
    for match in re.finditer(r'"([A-D])"\s*\{(.*?)\n        \}', script_text, re.S):
        body = match.group(2)
        pairs = re.findall(r'(?:^|"|`n)([A-Z][A-Z0-9_]*)=', body)
        if pairs:
            blocks[match.group(1)] = "\n".join(f"{k}=x" for k in pairs)
    return blocks


class EnvConsistencyTest(unittest.TestCase):
    def test_env_examples_keys_are_readable_by_config(self) -> None:
        """每个 ``.env.example`` 的键必须能被该服务的 config 读到。

        历史坏文件正是「键名不在 config 字段里」，这里把 ``.env.example``
        当作正样本：它必须与 config 对齐。
        """
        for code, service_dir in SERVICES.items():
            with self.subTest(service=code):
                fields = _config_fields(service_dir)
                example = ROOT / service_dir / ".env.example"
                keys = _env_keys(example.read_text(encoding="utf-8"))
                unknown = {k for k in keys if k.lower() not in fields}
                self.assertEqual(
                    unknown, set(),
                    f"{service_dir}/.env.example 含 config 读不到的键：{sorted(unknown)}",
                )

    def test_start_scripts_emit_keys_readable_by_config(self) -> None:
        """两个启动脚本给每个服务生成的键，都必须能被该服务 config 读到。"""
        for script_name in ("start_all.sh", "start_all.ps1"):
            script_text = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
            blocks = _extract_env_content_blocks(script_text)
            for code, service_dir in SERVICES.items():
                with self.subTest(script=script_name, service=code):
                    self.assertIn(
                        code, blocks,
                        f"{script_name} 未找到 {code} 服务的 .env 生成块",
                    )
                    fields = _config_fields(service_dir)
                    emitted = _env_keys(blocks[code])
                    unknown = {k for k in emitted if k.lower() not in fields}
                    self.assertEqual(
                        unknown, set(),
                        f"{script_name} 给 {code} 生成了 config 读不到的键：{sorted(unknown)}",
                    )
                    # B 的历史 bug 就是漏了这四个键（是「缺」而不是「多」）
                    required = _env_keys(
                        (ROOT / service_dir / ".env.example").read_text(encoding="utf-8")
                    )
                    missing = {
                        k for k in required
                        if k not in emitted
                        and k not in {"MODEL_VERSION", "CLIENT_TIMEOUT_SECONDS"}
                    }
                    self.assertEqual(
                        missing, set(),
                        f"{script_name} 给 {code} 漏了必需键：{sorted(missing)}",
                    )

    def test_no_localhost_in_config_or_env_examples(self) -> None:
        """config 与 .env.example 不得用 ``localhost``（Windows→IPv6 坑）。"""
        offenders: list[str] = []
        for service_dir in SERVICES.values():
            for rel in ("src/config.py", ".env.example"):
                path = ROOT / service_dir / rel
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8")
                for lineno, line in enumerate(text.splitlines(), 1):
                    if "localhost" in line:
                        offenders.append(f"{service_dir}/{rel}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "以下位置仍使用 localhost（Windows 上会优先解析 IPv6 ::1，"
            "而服务只监听 127.0.0.1）：\n" + "\n".join(offenders),
        )

    def test_service_ports_and_databases_are_isolated(self) -> None:
        """四服务端口与数据库 URL 必须互不相同（独立库，不共用）。"""
        ports: dict[str, str] = {}
        dbs: dict[str, str] = {}
        for code, service_dir in SERVICES.items():
            example = (ROOT / service_dir / ".env.example").read_text(encoding="utf-8")
            for line in example.splitlines():
                if re.match(r"^\s*\w*PORT\s*=", line):
                    ports[code] = line.split("=", 1)[1].strip()
                if re.match(r"^\s*\w*DATABASE_URL\s*=", line):
                    dbs[code] = line.split("=", 1)[1].strip()
        self.assertEqual(len(set(ports.values())), len(ports),
                         f"服务端口重复：{ports}")
        self.assertEqual(len(set(dbs.values())), len(dbs),
                         f"服务数据库重复：{dbs}")
        self.assertEqual(ports, {"A": "8101", "B": "8102", "C": "8103", "D": "8104"})

    def test_powershell_script_keeps_utf8_bom(self) -> None:
        """含中文的 .ps1 必须保留 UTF-8 BOM。

        Windows PowerShell 5.1 会按系统代码页（GBK 等）解码**无 BOM** 的
        ``.ps1``，中文字面量与错误提示会变成乱码。``start_all.ps1`` 含大量
        中文输出，且历史上真的被编辑工具悄悄剥掉过 BOM（fed6ba6），
        因此加此守护测试：非 ASCII 的 ps1 必须带 BOM，且不得重复前缀。
        """
        for name in ("start_all.ps1", "bootstrap.ps1"):
            path = ROOT / "scripts" / name
            if not path.exists():
                continue
            raw = path.read_bytes()
            with self.subTest(script=name):
                non_ascii = any(b > 127 for b in raw)
                if non_ascii:
                    self.assertEqual(
                        raw[:3], b"\xef\xbb\xbf",
                        f"{name} 含非 ASCII 字符却没有 UTF-8 BOM，"
                        "Windows PowerShell 5.1 会乱码",
                    )
                    self.assertNotEqual(
                        raw[:6], b"\xef\xbb\xbf\xef\xbb\xbf",
                        f"{name} 有重复 BOM 前缀",
                    )


if __name__ == "__main__":
    unittest.main()
