# 值日排班管理系统 — 生产部署镜像
FROM python:3.12-slim

# 不生成 .pyc、日志直连 stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先装依赖以利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 数据库放在 /data 卷中，重建容器不丢数据
RUN mkdir -p /data
ENV DUTY_SCHEDULER_DB=/data/duty_scheduler.db

EXPOSE 5001

# 中等并发建议 --workers 2 --threads 4（SQLite 不宜过多并发写）
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--threads", "4", "--timeout", "60", "wsgi:app"]
