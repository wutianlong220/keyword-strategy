#!/bin/bash
# 快速启动脚本

echo "🔍 关键词分析系统 (智谱GLM版)"
echo "=================="
echo ""

# 检查 .env 文件
if [ ! -f "../.env" ]; then
    echo "⚠️  未找到 .env 文件"
    echo ""
    echo "请创建 .env 文件并设置 API Key:"
    echo "  1. 复制示例: cp ../.env.example ../.env"
    echo "  2. 编辑文件: nano ../.env"
    echo "  3. 填入你的 API Key"
    echo ""
    echo "或者使用环境变量:"
    echo "  export ZHIPU_API_KEY='your-api-key-here'"
    echo ""
    exit 1
fi

# 运行分析
python3 analyze.py
