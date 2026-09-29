FROM python:3.11-slim

# Graphviz 是系統層級套件，這是之前無法用一般 serverless 平台部署的主因
RUN apt-get update \
    && apt-get install -y --no-install-recommends graphviz \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_DEBUG=false
EXPOSE 5000

# 正式環境用 gunicorn，不用 Flask 內建的開發用伺服器（官方文件本身就不建議拿來上線用）
# 一次鑑定要連打好幾次 LLM，常常超過 gunicorn 預設 sync worker 的 30 秒逾時，
# worker 會被直接砍掉、連線中斷。改用 gthread：請求在執行緒裡跑，不會觸發 worker 逾時，
# 串流回應也能一直送到結束。
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--worker-class", "gthread", "--threads", "4", "app:app"]
