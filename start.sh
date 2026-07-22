#!/bin/bash
# Wellcome 文档生成器 - 启动脚本
# 同事通过浏览器访问: http://你的IP:8501

cd "$(dirname "$0")"

# Check if streamlit is installed
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
fi

# Get local IP
IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")

echo "============================================"
echo "  Wellcome 文档生成器"
echo "============================================"
echo ""
echo "  本地访问: http://localhost:8501"
echo "  同事访问: http://$IP:8501"
echo ""
echo "  按 Ctrl+C 停止服务"
echo "============================================"
echo ""

python3 -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
