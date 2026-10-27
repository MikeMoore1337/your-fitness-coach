from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.base import Base


class FirstTouchAttribution(Base):
    """The first allowlisted acquisition context bound to one account."""

    __tablename__ = "first_touch_attributions"
    __table_args__ = (
        CheckConstraint(
            "first_touch_source IN ('google', 'yandex', 'telegram', 'direct', 'referral', 'utm')",
            name="ck_first_touch_attributions_source",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_touch_source: Mapped[str] = mapped_column(String(16), nullable=False)
    first_touch_medium: Mapped[str] = mapped_column(String(64), nullable=False)
    first_touch_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_landing_path: Mapped[str] = mapped_column(String(256), nullable=False)
    first_referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_touch_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    utm_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(128), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_msk_naive)
