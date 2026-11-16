from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.db.base import Base


class CoachNutritionProposal(Base):
    __tablename__ = "coach_nutrition_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_coach_nutrition_proposal_status",
        ),
        CheckConstraint(
            "version > 0 AND plan_revision >= 0", name="ck_coach_nutrition_proposal_versions"
        ),
        UniqueConstraint("coach_user_id", "create_key", name="uq_coach_nutrition_proposal_create"),
        UniqueConstraint("relationship_id", "version", name="uq_coach_nutrition_proposal_version"),
        Index("ix_coach_nutrition_proposal_client", "client_user_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_clients.id", ondelete="SET NULL"), nullable=True
    )
    coach_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    client_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    before: Mapped[dict] = mapped_column(JSON, nullable=False)
    create_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    decision_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
