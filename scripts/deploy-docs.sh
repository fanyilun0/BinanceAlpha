#!/bin/bash
#
# 本地构建 docs-viewer 并将 dist 推送到 gh-pages 分支
# Vercel 部署 gh-pages 分支的静态产物，不再依赖远端构建
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCS_DIR="$PROJECT_DIR/docs-viewer"
DIST_DIR="$DOCS_DIR/dist"
DEPLOY_BRANCH="gh-pages"

echo "=== docs-viewer 构建与部署 $(date '+%Y-%m-%d %H:%M:%S') ==="

# ---------- 1. 安装依赖并构建 ----------
cd "$DOCS_DIR"

if [ ! -d "node_modules" ]; then
    echo "[1/4] 安装 npm 依赖..."
    npm install --prefer-offline --no-audit --no-fund
else
    echo "[1/4] node_modules 已存在，跳过安装"
fi

echo "[2/4] 执行构建 (npm run build)..."
npm run build

if [ ! -d "$DIST_DIR" ] || [ -z "$(ls -A "$DIST_DIR")" ]; then
    echo "错误: 构建产物目录为空: $DIST_DIR"
    exit 1
fi

echo "[3/4] 构建完成，产物大小: $(du -sh "$DIST_DIR" | cut -f1)"

# ---------- 2. 将 dist 推送到 gh-pages 分支 ----------
echo "[4/4] 推送到 $DEPLOY_BRANCH 分支..."

cd "$PROJECT_DIR"
REMOTE_URL=$(git remote get-url origin)

# 使用临时目录操作，不影响主工作区
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

cd "$TEMP_DIR"
git init --initial-branch="$DEPLOY_BRANCH"
git remote add origin "$REMOTE_URL"

# 复制 dist 产物到临时仓库
cp -r "$DIST_DIR"/* .

git add -A
git commit -m "Deploy docs-viewer: $(date '+%Y-%m-%d %H:%M:%S')"
git push --force origin "$DEPLOY_BRANCH"

echo "=== 部署完成: $DEPLOY_BRANCH 分支已更新 ==="
