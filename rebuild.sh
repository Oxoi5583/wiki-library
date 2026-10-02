#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

BRANCH=$(git branch --show-current)
if [ -z "$BRANCH" ]; then
    echo "生成失敗：目前不是在 Git branch 上。" >&2
    exit 1
fi

echo "更新 repository：$BRANCH"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -x .venv/bin/python ]; then
    echo "建立 Python virtual environment..."
    python3 -m venv .venv
fi

echo "安裝／更新 Python dependencies..."
.venv/bin/python -m pip install -r requirements.txt

echo "生成 Wiki Library..."
.venv/bin/python build.py --output "/var/wiki/html/library"

echo "生成完成：/var/wiki/html/library"
