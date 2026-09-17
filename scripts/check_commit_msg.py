#!/usr/bin/env python3
"""Validate a commit message subject or pull request title."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


PATTERN = re.compile(
    r"^(feat|fix|docs|test|refactor|chore|ci|build|perf|revert)"
    r"\((a|b|c|d|shared|contract|docs)\): .{4,72}$"
)


def validate(subject: str) -> list[str]:
    errors: list[str] = []
    if "\n" in subject or "\r" in subject:
        subject = subject.splitlines()[0]
    if len(subject) > 100:
        errors.append("标题总长度不能超过 100 个字符")
    if not PATTERN.fullmatch(subject):
        errors.append(
            "格式应为 type(scope): 说明；type 使用 feat/fix/docs/test/refactor/"
            "chore/ci/build/perf/revert，scope 使用 a/b/c/d/shared/contract/docs"
        )
    if subject.endswith(("。", ".")):
        errors.append("标题末尾不加句号")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="检查提交标题或 PR 标题")
    parser.add_argument("message_file", nargs="?", help="Git commit-msg hook 传入的文件")
    parser.add_argument("--text", help="直接检查给定标题")
    args = parser.parse_args()

    if bool(args.message_file) == bool(args.text):
        parser.error("必须且只能提供 message_file 或 --text")

    if args.text is not None:
        subject = args.text.strip()
    else:
        subject = Path(args.message_file).read_text(encoding="utf-8").splitlines()[0].strip()

    errors = validate(subject)
    if errors:
        print(f"提交/PR 标题不符合规范：{subject!r}")
        for error in errors:
            print(f"- {error}")
        print("示例：feat(c): 实现 C-FR-14 备件查询")
        return 1

    print(f"标题格式通过：{subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
