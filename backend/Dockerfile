# syntax=docker/dockerfile:1

FROM node:24-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f AS frontend-build
WORKDIR /frontend
ARG VITE_PWA_ENABLED=true
ENV VITE_PWA_ENABLED=$VITE_PWA_ENABLED
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
# OS security updates arrive through the reviewed base-image digest refresh; do not add a
# mutable apt-get upgrade here because it breaks source-to-image reproducibility.
# shortcut: apt package versions remain repository-resolved; use a dated Debian snapshot only
# if byte-for-byte replay of OS package installation becomes a requirement.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libbrotli1=1.1.0-2+deb13u1 \
        libexpat1 \
        libgl1 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge "1.1.0-2+deb13u1" \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libexpat1)" ge "2.9.0-1~deb13u1" \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra backend --no-install-project
# The application runs from the locked venv; remove vulnerable build tooling inherited from the base image.
RUN python -m pip uninstall --yes pip setuptools wheel
ENV PATH="/app/.venv/bin:$PATH"
COPY scripts/fetch_rapidocr_models.py /app/scripts/fetch_rapidocr_models.py
COPY scripts/connection_budget_preflight.py scripts/trusted_runtime_collector.py /app/scripts/
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
