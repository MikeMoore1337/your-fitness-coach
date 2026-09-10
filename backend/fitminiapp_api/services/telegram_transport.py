from __future__ import annotations

from datetime import timedelta

from fitminiapp_api.core.config import settings


class TelegramPublicationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retry_after: timedelta | None = None,
        terminal: bool = False,
        uncertain: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.terminal = terminal
        self.uncertain = uncertain


def telegram_transport_options() -> dict[str, object]:
    """Return the explicit Bot API route without inheriting ambient proxy settings."""

    options: dict[str, object] = {"trust_env": False}
    if settings.telegram_bot_proxy_url:
        options["proxy"] = settings.telegram_bot_proxy_url
    return options
