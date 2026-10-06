FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libglib2.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS builder

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

FROM base AS runtime

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN mkdir -p /app/templates /app/uploads /tmp/.cache \
    && chown -R appuser:appuser /app \
    && chmod 777 /tmp/.cache

# WeasyPrint требует доступный кэш шрифтов
ENV XDG_CACHE_HOME=/tmp/.cache

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]