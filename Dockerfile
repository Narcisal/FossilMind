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
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
