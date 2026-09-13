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
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-runtime.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-runtime.txt && pip check
RUN useradd --create-home --uid 10001 appuser
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
