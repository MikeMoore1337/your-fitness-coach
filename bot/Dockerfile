# syntax=docker/dockerfile:1

FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra bot --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lock/fitminiapp-bot \
    && chown appuser:appuser /var/lock/fitminiapp-bot
COPY --chown=appuser:appuser bot/ .
USER appuser
CMD ["python", "-m", "fitminiapp_bot.bot"]
