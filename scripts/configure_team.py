#!/usr/bin/env python3
"""Generate .github/CODEOWNERS from four GitHub usernames."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


USERNAME_RE = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$")


def normalize_username(value: str) -> str:
    username = value.strip().lstrip("@")
    if not USERNAME_RE.fullmatch(username):
        raise argparse.ArgumentTypeError(
            f"无效的 GitHub 用户名：{value!r}。只允许字母、数字和单个连字符。"
        )
    return username


def main() -> int:
    parser = argparse.ArgumentParser(description="生成四人项目的 CODEOWNERS")
    parser.add_argument("--a", required=True, type=normalize_username, help="成员 A 用户名")
    parser.add_argument("--b", required=True, type=normalize_username, help="成员 B 用户名")
    parser.add_argument("--c", required=True, type=normalize_username, help="成员 C 用户名")
    parser.add_argument("--d", required=True, type=normalize_username, help="成员 D 用户名")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    template_path = root / ".github" / "CODEOWNERS.template"
    output_path = root / ".github" / "CODEOWNERS"

    if not template_path.exists():
        raise SystemExit(f"缺少模板：{template_path}")

    content = template_path.read_text(encoding="utf-8")
    replacements = {
        "__MEMBER_A__": args.a,
        "__MEMBER_B__": args.b,
        "__MEMBER_C__": args.c,
        "__MEMBER_D__": args.d,
    }
    for placeholder, username in replacements.items():
        content = content.replace(placeholder, username)

    output_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"已生成 {output_path.relative_to(root)}")
    print(f"A=@{args.a}  B=@{args.b}  C=@{args.c}  D=@{args.d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
