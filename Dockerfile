FROM python:3.10-slim

WORKDIR /app

# Install system deps for Playwright (Chromium) + Build Tools for LXML/Pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc wget curl gnupg libnss3 libatk-bridge2.0-0 libdrm2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpangocairo-1.0-0 libgtk-3-0 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install all pinned dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ app/
COPY smoke_test.py .
COPY run.py .

# Create dirs
RUN mkdir -p /app/data /app/logs

EXPOSE ${PORT:-10000}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

CMD ["python", "run.py"]
