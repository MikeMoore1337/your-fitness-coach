"""Add canonical Web article candidates, content and immutable revisions.

Revision ID: 0072_web_articles_lifecycle
Revises: 0071_hermes_intake_taxonomy
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_web_articles_lifecycle"
down_revision: str | None = "0071_hermes_intake_taxonomy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

online_rollout_phase = "expand"
online_rollout_notes = (
    "Adds the canonical Web editorial lifecycle; only published rows are eligible for public routes."
)


def upgrade() -> None:
    op.create_table(
        "web_article_candidates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("working_title", sa.String(length=240), nullable=False),
        sa.Column("primary_topic", sa.String(length=64), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("article_kind", sa.String(length=32), nullable=False),
        sa.Column("search_intent", sa.String(length=24), nullable=False),
        sa.Column("primary_query", sa.String(length=240), nullable=False),
        sa.Column("secondary_queries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("audience", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("evidence_level", sa.String(length=32), nullable=False, server_default="unknown"),
        *(
            sa.Column(name, sa.Integer(), nullable=False, server_default="0")
            for name in (
                "search_demand_signal",
                "intent_clarity",
                "topical_relevance",
                "product_relevance",
                "audience_usefulness",
                "evergreen_potential",
                "evidence_availability",
                "existing_content_overlap",
                "internal_link_potential",
                "risk_review_cost",
                "freshness_need",
                "news_opportunity",
            )
        ),
        sa.Column("priority_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "web_article_potential_reasons", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'researching', 'draft', 'review', 'rejected')",
            name="ck_web_article_candidates_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('manual', 'seo_import', 'news_handoff')",
            name="ck_web_article_candidates_source_kind",
        ),
        sa.CheckConstraint(
            "search_demand_signal BETWEEN 0 AND 100 AND intent_clarity BETWEEN 0 AND 100 "
            "AND topical_relevance BETWEEN 0 AND 100 AND product_relevance BETWEEN 0 AND 100 "
            "AND audience_usefulness BETWEEN 0 AND 100 AND evergreen_potential BETWEEN 0 AND 100 "
            "AND evidence_availability BETWEEN 0 AND 100 AND existing_content_overlap BETWEEN 0 AND 100 "
            "AND internal_link_potential BETWEEN 0 AND 100 AND risk_review_cost BETWEEN 0 AND 100 "
            "AND freshness_need BETWEEN 0 AND 100 AND news_opportunity BETWEEN 0 AND 100",
            name="ck_web_article_candidate_signals",
        ),
        sa.CheckConstraint("priority_score BETWEEN 0 AND 100", name="ck_web_article_candidate_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_web_article_candidates_queue",
        "web_article_candidates",
        ["status", "priority_score", "updated_at"],
    )

    op.create_table(
        "web_articles",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(length=32),
            sa.ForeignKey("web_article_candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.String(length=320), nullable=False),
        sa.Column("lead", sa.Text(), nullable=False),
        sa.Column("body_sections", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("article_kind", sa.String(length=32), nullable=False),
        sa.Column("search_intent", sa.String(length=24), nullable=False),
        sa.Column("primary_query", sa.String(length=240), nullable=False),
        sa.Column("secondary_queries", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("evidence_level", sa.String(length=32), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("claim_source_matrix", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("author", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("editor", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("domain_reviewer", sa.JSON(), nullable=True),
        sa.Column("canonical_url", sa.String(length=512), nullable=True),
        sa.Column("related_slugs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evergreen_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_relevance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("editorial_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "web_article_potential_reasons", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("research_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("skill_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("generated_with_ai", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("research_assistance", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("correction_reason", sa.String(length=256), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "status IN ('candidate', 'researching', 'draft', 'review', 'approved', 'published', "
            "'update_required', 'archived', 'retracted')",
            name="ck_web_articles_status",
        ),
        sa.CheckConstraint("content_version >= 1", name="ck_web_articles_content_version"),
        sa.CheckConstraint("evergreen_score BETWEEN 0 AND 100", name="ck_web_articles_evergreen"),
        sa.CheckConstraint(
            "product_relevance BETWEEN 0 AND 100", name="ck_web_articles_product_relevance"
        ),
        sa.CheckConstraint(
            "editorial_value BETWEEN 0 AND 100", name="ck_web_articles_editorial_value"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_web_articles_candidate_id", "web_articles", ["candidate_id"])
    op.create_index("ix_web_articles_public_queue", "web_articles", ["status", "updated_at"])

    op.create_table(
        "web_article_revisions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "article_id",
            sa.String(length=32),
            sa.ForeignKey("web_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("content_version >= 1", name="ck_web_article_revision_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "content_version", name="uq_web_article_revision_version"),
    )
    op.create_index(
        "ix_web_article_revisions_article_created",
        "web_article_revisions",
        ["article_id", "created_at"],
    )

    op.create_table(
        "hermes_web_article_submissions",
        sa.Column("submission_id", sa.String(length=64), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(length=32),
            sa.ForeignKey("web_article_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.String(length=32),
            sa.ForeignKey("web_articles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_nonce", sa.String(length=128), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("research_version", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("skill_version", sa.String(length=64), nullable=False),
        sa.Column("response_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="accepted"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('accepted', 'expired')",
            name="ck_hermes_web_article_submissions_status",
        ),
        sa.PrimaryKeyConstraint("submission_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_hermes_web_article_idempotency"),
        sa.UniqueConstraint("request_nonce", name="uq_hermes_web_article_nonce"),
    )
    op.create_index(
        "ix_hermes_web_article_submissions_created",
        "hermes_web_article_submissions",
        ["created_at"],
    )
    op.create_index(
        "ix_hermes_web_article_submissions_expires_status",
        "hermes_web_article_submissions",
        ["expires_at", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hermes_web_article_submissions_expires_status",
        table_name="hermes_web_article_submissions",
    )
    op.drop_index(
        "ix_hermes_web_article_submissions_created",
        table_name="hermes_web_article_submissions",
    )
    op.drop_table("hermes_web_article_submissions")
    op.drop_index(
        "ix_web_article_revisions_article_created", table_name="web_article_revisions"
    )
    op.drop_table("web_article_revisions")
    op.drop_index("ix_web_articles_public_queue", table_name="web_articles")
    op.drop_index("ix_web_articles_candidate_id", table_name="web_articles")
    op.drop_table("web_articles")
    op.drop_index("ix_web_article_candidates_queue", table_name="web_article_candidates")
    op.drop_table("web_article_candidates")
