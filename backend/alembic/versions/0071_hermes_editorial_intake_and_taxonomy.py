"""Add Hermes intake receipts and independent news taxonomy fields.

Revision ID: 0071_hermes_intake_taxonomy
Revises: 0070_browser_oauth_transactions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0071_hermes_intake_taxonomy"
down_revision: str | None = "0070_browser_oauth_transactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds nullable taxonomy compatibility columns without rewrite defaults and an "
    "append-only, replay-protected Hermes intake receipt table."
)


def upgrade() -> None:
    op.add_column(
        "news_clusters", sa.Column("primary_topic", sa.String(length=64), nullable=True)
    )
    op.add_column("news_clusters", sa.Column("topics", sa.JSON(), nullable=True))
    op.add_column(
        "news_clusters", sa.Column("content_type", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("product_class", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("evidence_level", sa.String(length=32), nullable=True)
    )
    op.add_column("news_clusters", sa.Column("risk_level", sa.String(length=32), nullable=True))
    op.add_column("news_clusters", sa.Column("audience", sa.String(length=32), nullable=True))
    op.add_column("news_clusters", sa.Column("geography", sa.JSON(), nullable=True))
    op.add_column(
        "news_clusters", sa.Column("classification_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("classification_reasons", sa.JSON(), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("discovery_eligible", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("discovery_reasons", sa.JSON(), nullable=True)
    )
    op.add_column(
        "news_clusters", sa.Column("publication_policy", sa.String(length=32), nullable=True)
    )
    op.add_column("news_clusters", sa.Column("risk_reasons", sa.JSON(), nullable=True))
    op.add_column(
        "news_clusters", sa.Column("risk_policy_version", sa.String(length=64), nullable=True)
    )

    op.create_table(
        "hermes_editorial_submissions",
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column(
            "source_id",
            sa.String(length=64),
            sa.ForeignKey("news_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_nonce", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="accepted"),
        sa.Column(
            "cluster_id",
            sa.String(length=32),
            sa.ForeignKey("news_clusters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "draft_id",
            sa.String(length=32),
            sa.ForeignKey("news_draft_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("skill_version", sa.String(length=64), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=False),
        sa.Column("risk_policy_version", sa.String(length=64), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("response_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rejection_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('accepted', 'rejected', 'expired')",
            name="ck_hermes_editorial_submissions_status",
        ),
        sa.CheckConstraint("source_count BETWEEN 1 AND 20", name="ck_hermes_source_count"),
        sa.PrimaryKeyConstraint("submission_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_hermes_submission_idempotency"),
        sa.UniqueConstraint("request_nonce", name="uq_hermes_submission_nonce"),
    )
    op.create_index(
        "ix_hermes_submissions_created",
        "hermes_editorial_submissions",
        ["created_at"],
    )
    op.create_index(
        "ix_hermes_submissions_expires_status",
        "hermes_editorial_submissions",
        ["expires_at", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hermes_submissions_expires_status", table_name="hermes_editorial_submissions"
    )
    op.drop_index("ix_hermes_submissions_created", table_name="hermes_editorial_submissions")
    op.drop_table("hermes_editorial_submissions")
    for column in (
        "risk_policy_version",
        "risk_reasons",
        "publication_policy",
        "discovery_reasons",
        "discovery_eligible",
        "classification_reasons",
        "classification_version",
        "geography",
        "audience",
        "risk_level",
        "evidence_level",
        "product_class",
        "content_type",
        "topics",
        "primary_topic",
    ):
        op.drop_column("news_clusters", column)
