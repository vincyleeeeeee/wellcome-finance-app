#!/bin/bash
# Wellcome 财务平台 — 部署脚本
# 使用方法：在终端运行 bash deploy.sh

set -e

echo "========================================"
echo "  Wellcome 财务平台 — 部署到 GitHub"
echo "========================================"

cd "$(dirname "$0")"

# 1. Init git
if [ ! -d ".git" ]; then
    echo "📦 初始化 Git..."
    git init
    git add -A
    git commit -m "Initial: Wellcome财务自动化平台"
fi

# 2. Login to GitHub
echo ""
echo "🔐 登录 GitHub..."
gh auth login

# 3. Create repo
echo ""
echo "📁 创建 GitHub 仓库..."
gh repo create wellcome-finance-app --private --source=. --remote=origin --push

echo ""
echo "========================================"
echo "  ✅ 代码已推送到 GitHub！"
echo "========================================"
echo ""
echo "下一步：打开 https://share.streamlit.io"
echo "  1. 用 GitHub 账号登录"
echo "  2. 点 New App"
echo "  3. 选择仓库: vincyleeeeeee/wellcome-finance-app"
echo "  4. Branch: main"
echo "  5. Main file path: app.py"
echo "  6. 点 Deploy"
echo ""
echo "部署完成后，在 Streamlit Cloud 的 Settings → Secrets 中添加："
echo "  SUPABASE_URL = https://iadfdtpjnemswwtnkygj.supabase.co"
echo "  SUPABASE_KEY = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZGZkdHBqbmVtc3d3dG5reWdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ3MTA4NzAsImV4cCI6MjEwMDI4Njg3MH0.nWMuVuT80fNKujtl7Cgrojx2uD55Oe8URGLdfo1FxGo"
echo ""
echo "部署完成后，只有登录用户才能使用系统。"
