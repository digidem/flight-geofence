FROM python:3.12-slim-bookworm

ARG APP_VERSION=0.5.2

LABEL org.opencontainers.image.title="Flight Geofence Alerts" \
      org.opencontainers.image.description="Protected-area aircraft monitoring proof of concept" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/runtime /data/downloads \
    && chown -R app:app /data /app

COPY --chown=app:app app ./app

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=6s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
