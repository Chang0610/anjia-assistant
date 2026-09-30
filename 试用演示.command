#!/bin/zsh
cd "${0:A:h}" || exit 1
export DEMO_MODE=1
echo "本地演示模式：不会调用大模型。请在浏览器打开 http://127.0.0.1:8765"
python3 backend/server.py
