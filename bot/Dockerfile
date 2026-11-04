# syntax=docker/dockerfile:1

# Python 3.14.10 (security maintenance), immutable multi-platform image digest.
FROM python:3.14-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /uvx /bin/
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
