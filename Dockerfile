FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY mission-control/ mission-control/

RUN mkdir -p /app/data /app/app/data /app/logs

EXPOSE ${PORT:-18790}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-18790}/health || exit 1

CMD ["sh", "-c", "python app/worker.py & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-18790}"]
