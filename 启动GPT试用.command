#!/bin/zsh
cd "${0:A:h}" || exit 1
export PORT=8766
echo "GPT 试用页面：http://127.0.0.1:8766"
echo "请先在项目根目录的 .env.local 填入 OPENAI_API_KEY。"
python3 backend/server.py
