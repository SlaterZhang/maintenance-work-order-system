#!/usr/bin/env sh
set -eu

repository_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$repository_root" ]; then
  echo "请在 Git 仓库中运行本脚本。若尚未初始化，请先执行 git init。" >&2
  exit 1
fi

cd "$repository_root"

if [ "$#" -eq 4 ]; then
  python scripts/configure_team.py --a "$1" --b "$2" --c "$3" --d "$4"
elif [ "$#" -ne 0 ]; then
  echo "用法：./scripts/bootstrap.sh GitHub用户名A GitHub用户名B GitHub用户名C GitHub用户名D" >&2
  exit 1
else
  echo "警告：未生成 CODEOWNERS。负责人应带四个 GitHub 用户名重新运行。" >&2
fi

git config core.hooksPath .githooks
python -m pip install -r requirements-dev.txt
python scripts/check_repo.py
python -m unittest discover -s tests -p 'test_*.py'

echo "本地初始化完成。请检查 CODEOWNERS，并按 docs/05_GitHub仓库设置.md 保护 main。"
