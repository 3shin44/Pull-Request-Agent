FROM python:3.11-slim

# 安裝 Git、Curl 與基礎編譯工具（有些 Python 套件編譯需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 建立 AI 的工作目錄
WORKDIR /workspace

# 預先安裝常見的 Python 測試與開發套件，加速 AI 執行速度
RUN pip install --no-cache-dir pytest pytest-mock flake8 black

# 複製啟動腳本：用來在容器啟動時，動態將 .env 的 Token 寫入 Git 全域設定
RUN echo '#!/bin/bash\n\
if [ -n "$GITHUB_EMAIL" ] && [ -n "$GITHUB_USERNAME" ]; then\n\
    git config --global user.email "$GITHUB_EMAIL"\n\
    git config --global user.name "$GITHUB_USERNAME"\n\
fi\n\
if [ -n "$GITHUB_TOKEN" ]; then\n\
    git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"\n\
fi\n\
exec "$@"' > /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# 讓容器保持運行，等待 tools.py 透過 exec_run 丟指令進來
CMD ["sleep", "infinity"]