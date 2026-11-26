FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# jemalloc allocator (installed above): aggressively returns freed page memory to
# the OS (dirty/muzzy decay), keeping RSS low on the 512MB tier during the
# crawl-heavy enrichment/waterfall passes that were OOM-restarting the instance.
# ~10x less RSS creep than glibc malloc in FastAPI benchmarks. Set after pip so the
# build itself uses the default allocator; only the runtime process is preloaded.
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2
ENV MALLOC_CONF=background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000

COPY app/ app/
COPY config/ config/
COPY mission-control/ mission-control/

RUN mkdir -p /app/data /app/app/data /app/logs

EXPOSE ${PORT:-18790}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-18790}/health || exit 1

# `exec` makes uvicorn PID 1. Without it, dash (python:3.12-slim) stays PID 1,
# does not forward Render's SIGTERM, and uvicorn is SIGKILLed after the grace
# period, so the lifespan shutdown backup in app/main.py never ran: three
# deploys on 2026-11-26 produced no shutdown snapshot.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-18790}"]
