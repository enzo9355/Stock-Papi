# 使用輕量級 Python 3.10 映像檔
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 設定環境變數，讓 Python 輸出直接印在終端機（不緩衝），並避免產生 .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 安裝系統必要套件 (例如編譯 C++ 擴充套件可能需要的)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式原始碼與靜態檔案
COPY . .

# 預設開放 Port 5000 (Cloud Run 會自動注入 $PORT 變數)
ENV PORT 5000
EXPOSE 5000

# 使用 Gunicorn 啟動 Flask 伺服器
# 設定 1 個 worker 與 8 個 threads 來最佳化並行處理
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
