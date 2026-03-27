#!/bin/bash
# 独龙工具集 - 一键安装脚本（支持 macOS / Windows / Linux）

set -e

echo "🎙️ 独龙工具集安装脚本"
echo "======================"
echo "平台: $(uname -s)"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        echo "使用 python 而不是 python3"
    else
        echo "❌ 需要 Python3，请先安装"
        exit 1
    fi
fi
PYTHON=${PYTHON:-python3}
echo "✅ Python 已安装: $($PYTHON --version)"

# 检查 ffmpeg
FFMPEG_CMD=""
if command -v ffmpeg &> /dev/null; then
    FFMPEG_CMD="ffmpeg"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew &> /dev/null; then
        echo "⚠️ ffmpeg 未安装，正在安装..."
        brew install ffmpeg
        FFMPEG_CMD="ffmpeg"
    else
        echo "❌ 请先安装 Homebrew: https://brew.sh"
        exit 1
    fi
elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "win32"* ]]; then
    # Windows: 检查是否在 PATH 中
    if command -v ffmpeg.exe &> /dev/null || where ffmpeg &> /dev/null 2>&1; then
        FFMPEG_CMD="ffmpeg"
    else
        echo "⚠️ ffmpeg 未安装"
        echo "   Windows 用户请下载: https://ffmpeg.org/download.html"
        echo "   或使用 winget: winget install ffmpeg"
    fi
else
    # Linux
    if command -v apt-get &> /dev/null; then
        echo "⚠️ ffmpeg 未安装，正在安装..."
        sudo apt-get install -y ffmpeg || echo "请手动安装 ffmpeg"
    elif command -v yum &> /dev/null; then
        echo "⚠️ ffmpeg 未安装，正在安装..."
        sudo yum install -y ffmpeg || echo "请手动安装 ffmpeg"
    fi
    FFMPEG_CMD="ffmpeg"
fi

if [ -n "$FFMPEG_CMD" ]; then
    echo "✅ ffmpeg 已安装: $(ffmpeg -version | head -1)"
fi

# 安装 Python 依赖
echo ""
echo "📦 安装 Python 依赖..."
$PYTHON -m pip install pygame requests flask pysilk silk-python pyperclip

# Windows 额外依赖
if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "win32"* ]]; then
    echo "📦 安装 Windows 额外依赖..."
    $PYTHON -m pip install pyautogui pywin32 2>/dev/null || echo "pyautogui/pywin32 安装失败，请手动安装"
fi

# 获取安装目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "✅ 安装完成！"
echo ""
echo "📁 安装目录: $SKILL_DIR"
echo ""
echo "🚀 启动 TTS 服务:"
echo "   $PYTHON $SCRIPT_DIR/dulong_tts_server.py"
echo ""
echo "📝 配置说明:"
echo "   1. 编辑 $SCRIPT_DIR/dulong_tts_server.py 配置飞书凭证"
echo "   2. 在 OpenClaw/QClaw 中配置 TTS baseUrl 为 http://localhost:8765"
echo ""
echo "📖 详细文档: $SKILL_DIR/README.md"
