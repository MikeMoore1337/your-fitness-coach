# syntax=docker/dockerfile:1

# Python 3.14.10 (security maintenance), immutable multi-platform image digest.
FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
# Install the security update until the pinned base image includes it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --extra bot --no-install-project
# The application runs from the locked venv; remove vulnerable build tooling inherited from the base image.
RUN python -m pip uninstall --yes pip setuptools wheel
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lock/fitminiapp-bot \
    && chown appuser:appuser /var/lock/fitminiapp-bot
COPY --chown=appuser:appuser bot/ .
USER appuser
CMD ["python", "-m", "fitminiapp_bot.bot"]
