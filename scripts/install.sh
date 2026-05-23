#!/bin/bash
set -e

REPO="brandnewmax/DS2Claude"
BRANCH="main"
INSTALL_DIR="$HOME/.ds2claude"

echo ""
echo "  DS2Claude 一键安装"
echo "  ─────────────────"
echo ""

# ── 检查 Python ──
PYTHON=""
for cmd in python3 python; do
  if command -v $cmd &>/dev/null; then
    ver=$($cmd -c "import sys; print(sys.version_info[:2])" 2>/dev/null || echo "0")
    major=$(echo "$ver" | cut -d' ' -f1 | tr -d '(),' | cut -d',' -f1)
    if [ "$major" -ge 3 ] 2>/dev/null; then
      PYTHON=$cmd
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "  ❌ 需要 Python 3.9+，请先安装 Python"
  echo "     macOS: brew install python3"
  echo "     Ubuntu: sudo apt install python3 python3-pip"
  exit 1
fi

echo "  ✓ Python: $($PYTHON --version)"

# ── 下载 ──
if [ -d "$INSTALL_DIR" ]; then
  echo "  ✓ 目录已存在，更新文件…"
  cd "$INSTALL_DIR"
  if git rev-parse --git-dir &>/dev/null; then
    git pull origin "$BRANCH" --ff-only 2>/dev/null || echo "  ⚠ git pull 失败，跳过"
  fi
else
  echo "  ↓ 下载 DS2Claude…"
  git clone -b "$BRANCH" "https://github.com/${REPO}.git" "$INSTALL_DIR" --depth 1
  cd "$INSTALL_DIR"
fi

# ── 安装依赖 ──
echo "  ↓ 安装 Python 依赖…"
$PYTHON -m pip install -r requirements.txt --quiet 2>&1 | tail -1

# ── 检查配置 ──
if [ ! -f "$INSTALL_DIR/groups.yaml" ]; then
  echo "  ⚠ groups.yaml 不存在，请确认仓库完整性"
  exit 1
fi

echo ""
echo "  ✅ DS2Claude 安装完成！"
echo ""
echo "  目录: $INSTALL_DIR"
echo ""
echo "  接下来："
echo "    1. 编辑 API Key:  vim $INSTALL_DIR/groups.yaml"
echo "    2. 启动代理:      cd $INSTALL_DIR && python3 proxy.py"
echo "    3. 管理界面:      http://127.0.0.1:8765"
echo ""
echo "  Claude Desktop Gateway 设置:"
echo "    Base URL: http://127.0.0.1:8765"
echo "    Models:   claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5"
echo ""
