# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend-build
WORKDIR /frontend
ARG VITE_PWA_ENABLED=true
ENV VITE_PWA_ENABLED=$VITE_PWA_ENABLED
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libgl1 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra backend --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
COPY scripts/fetch_rapidocr_models.py /app/scripts/fetch_rapidocr_models.py
RUN python /app/scripts/fetch_rapidocr_models.py --output /opt/rapidocr/models
RUN useradd --create-home --uid 10001 appuser
RUN chmod 0555 /opt/rapidocr/models \
    && chmod 0444 /opt/rapidocr/models/*.onnx
COPY --chown=appuser:appuser backend/assets/ ./assets/
COPY --chown=appuser:appuser backend/alembic/ ./alembic/
COPY --chown=appuser:appuser backend/fitminiapp_api/ ./fitminiapp_api/
COPY --chown=appuser:appuser backend/alembic.ini backend/docker-entrypoint.sh backend/worker-entrypoint.sh backend/setup-entrypoint.sh ./
COPY --chown=appuser:appuser scripts/check_deployment.py /app/scripts/check_deployment.py
COPY --from=frontend-build --chown=appuser:appuser /frontend/dist /app/frontend-dist
COPY --from=frontend-build --chown=appuser:appuser /frontend/src/content/publicContent.json /app/frontend-dist/publicContent.json
RUN chmod +x /app/docker-entrypoint.sh /app/worker-entrypoint.sh /app/setup-entrypoint.sh
USER appuser
CMD ["/app/docker-entrypoint.sh"]
