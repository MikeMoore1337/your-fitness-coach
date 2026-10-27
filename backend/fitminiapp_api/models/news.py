from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fitminiapp_api.db.base import Base


class NewsSource(Base):
    __tablename__ = "news_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('primary_research', 'systematic_review', 'official_organization', "
            "'official_product', 'reputable_secondary', 'yfc')",
            name="ck_news_sources_type",
        ),
        CheckConstraint(
            "fetch_kind IN ('rss', 'json_feed', 'html_metadata')",
            name="ck_news_sources_fetch_kind",
        ),
        CheckConstraint(
            "fetch_interval_minutes BETWEEN 15 AND 10080",
            name="ck_news_sources_fetch_interval",
        ),
        Index("ix_news_sources_due", "enabled", "next_fetch_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fetch_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=360)
    trust_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    licensing_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fetch_options: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NewsCluster(Base):
    __tablename__ = "news_clusters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('clustered', 'rejected_by_rules', 'candidate', 'draft_ready', "
            "'image_pending', 'awaiting_review', 'deferred', 'rejected', "
            "'accepted_for_design', 'publication_approved', 'publication_scheduled', "
            "'publication_failed', 'published')",
            name="ck_news_clusters_status",
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_news_clusters_score"),
        CheckConstraint(
            "generation_attempt_count BETWEEN 0 AND 20",
            name="ck_news_clusters_generation_attempts",
        ),
        Index("ix_news_clusters_work_queue", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="clustered")
    primary_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    topic: Mapped[str] = mapped_column(String(48), nullable=False, default="other")
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_version: Mapped[str] = mapped_column(String(32), nullable=False, default="news-score-v1")
    score_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    conflict_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    primary_topic: Mapped[str | None] = mapped_column(String(64), nullable=True, default="unknown")
    topics: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default="explainer")
    product_class: Mapped[str | None] = mapped_column(String(32), nullable=True, default="unknown")
    evidence_level: Mapped[str | None] = mapped_column(String(32), nullable=True, default="unknown")
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True, default="unknown")
    audience: Mapped[str | None] = mapped_column(String(32), nullable=True, default="general")
    geography: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    classification_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="news-taxonomy-v1"
    )
    classification_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    discovery_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    discovery_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    publication_policy: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="manual_required"
    )
    risk_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    risk_policy_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="news-risk-v1"
    )
    merge_reason: Mapped[str] = mapped_column(String(160), nullable=False, default="new_event")
    latest_draft_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_image_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_image_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deferred_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('fetched', 'clustered', 'rejected_by_rules')",
            name="ck_news_items_status",
        ),
        UniqueConstraint(
            "source_id", "external_id_hash", "content_hash", name="uq_news_items_source_revision"
        ),
        Index("ix_news_items_url_hash", "canonical_url_hash"),
        Index("ix_news_items_doi", "doi"),
        Index("ix_news_items_cluster", "cluster_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("news_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="fetched")
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    external_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(160), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merge_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="new_event")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class NewsDraftRevision(Base):
    __tablename__ = "news_draft_revisions"
    __table_args__ = (
        UniqueConstraint("cluster_id", "revision", name="uq_news_draft_cluster_revision"),
        CheckConstraint("revision >= 1", name="ck_news_draft_revision_positive"),
        CheckConstraint("generation_latency_ms >= 0", name="ck_news_draft_latency"),
        Index("ix_news_drafts_cluster_created", "cluster_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    primary_item_id: Mapped[int] = mapped_column(
        ForeignKey("news_items.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_item_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generation_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_cost_microunits: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class NewsReviewDelivery(Base):
    __tablename__ = "news_review_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'sent', 'failed', 'cancelled')",
            name="ck_news_review_deliveries_status",
        ),
        UniqueConstraint(
            "draft_id", "recipient_ref", "delivery_round", name="uq_news_review_delivery_round"
        ),
        Index(
            "ix_news_review_delivery_queue",
            "next_attempt_at",
            postgresql_where=text("status = 'queued'"),
            sqlite_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_ref: Mapped[str] = mapped_column(String(24), nullable=False)
    delivery_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NewsEditorialAction(Base):
    __tablename__ = "news_editorial_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('skip', 'defer', 'regenerate', 'accept_for_design')",
            name="ck_news_editorial_actions_action",
        ),
        UniqueConstraint(
            "draft_id", "actor_ref", "action", name="uq_news_editorial_action_idempotency"
        ),
        Index("ix_news_editorial_actions_cluster_created", "cluster_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="CASCADE"), nullable=False
    )
    actor_ref: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class NewsStateTransition(Base):
    __tablename__ = "news_state_transitions"
    __table_args__ = (
        Index("ix_news_state_transitions_cluster_created", "cluster_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class NewsImageRevision(Base):
    __tablename__ = "news_image_revisions"
    __table_args__ = (
        UniqueConstraint("cluster_id", "revision", name="uq_news_image_cluster_revision"),
        CheckConstraint("revision >= 1", name="ck_news_image_revision_positive"),
        CheckConstraint(
            "kind IN ('generated', 'template', 'uploaded')",
            name="ck_news_image_kind",
        ),
        CheckConstraint(
            "safety_status IN ('generated_pending_review', 'owner_uploaded', 'template')",
            name="ck_news_image_safety_status",
        ),
        CheckConstraint("byte_size > 0", name="ck_news_image_byte_size"),
        CheckConstraint("width > 0 AND height > 0", name="ck_news_image_dimensions"),
        Index("ix_news_images_cluster_created", "cluster_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    text_revision_id: Mapped[str] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    safety_status: Mapped[str] = mapped_column(String(32), nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generation_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_cost_microunits: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class NewsReviewDecision(Base):
    __tablename__ = "news_review_decisions"
    __table_args__ = (
        CheckConstraint(
            "publication_mode IN ('immediate', 'scheduled')",
            name="ck_news_review_publication_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'consumed', 'cancelled')",
            name="ck_news_review_decision_status",
        ),
        CheckConstraint(
            "(image_revision_id IS NULL AND explicit_no_image) OR "
            "(image_revision_id IS NOT NULL AND NOT explicit_no_image)",
            name="ck_news_review_exact_image",
        ),
        Index("ix_news_review_decisions_cluster", "cluster_id", "approved_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    text_revision_id: Mapped[str] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    image_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("news_image_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    explicit_no_image: Mapped[bool] = mapped_column(Boolean, nullable=False)
    target_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    publication_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_for_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_ref: Mapped[str] = mapped_column(String(24), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NewsPublicationSnapshot(Base):
    __tablename__ = "news_publication_snapshots"
    __table_args__ = (
        CheckConstraint(
            "publication_mode IN ('immediate', 'scheduled')",
            name="ck_news_publication_mode",
        ),
        CheckConstraint(
            "status IN ('queued', 'scheduled', 'processing', 'published', 'failed', "
            "'uncertain', 'cancelled')",
            name="ck_news_publication_status",
        ),
        CheckConstraint(
            "transport IN ('message', 'photo')",
            name="ck_news_publication_transport",
        ),
        CheckConstraint(
            "parse_mode IS NULL OR parse_mode IN ('HTML')",
            name="ck_news_publication_parse_mode",
        ),
        UniqueConstraint("decision_id", name="uq_news_publication_decision"),
        UniqueConstraint("idempotency_key", name="uq_news_publication_idempotency"),
        Index(
            "ix_news_publication_queue",
            "next_attempt_at",
            postgresql_where=text("status IN ('queued', 'scheduled')"),
            sqlite_where=text("status IN ('queued', 'scheduled')"),
        ),
        Index(
            "ix_news_publication_channel_day",
            "target_channel_id",
            "publication_local_date",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("news_review_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="CASCADE"), nullable=False
    )
    text_revision_id: Mapped[str] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    image_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("news_image_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    target_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_channel_username: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    publication_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    publication_local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_ref: Mapped[str] = mapped_column(String(24), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    urgent_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publication_text: Mapped[str] = mapped_column(Text, nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    parse_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    link_preview_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telegram_permalink: Mapped[str | None] = mapped_column(String(512), nullable=True)
    telegram_edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telegram_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    post_edit_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class HermesEditorialSubmission(Base):
    """Replay-protected, privacy-safe receipt for the external Hermes intake boundary."""

    __tablename__ = "hermes_editorial_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'rejected', 'expired')",
            name="ck_hermes_editorial_submissions_status",
        ),
        CheckConstraint("source_count BETWEEN 1 AND 20", name="ck_hermes_source_count"),
        UniqueConstraint("idempotency_key", name="uq_hermes_submission_idempotency"),
        UniqueConstraint("request_nonce", name="uq_hermes_submission_nonce"),
        Index("ix_hermes_submissions_created", "created_at"),
        Index("ix_hermes_submissions_expires_status", "expires_at", "status"),
    )

    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("news_sources.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("news_clusters.id", ondelete="SET NULL"), nullable=True
    )
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("news_draft_revisions.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(64), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    response_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebArticleCandidate(Base):
    """Provider-neutral article idea and scoring receipt; never a publish instruction."""

    __tablename__ = "web_article_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'approved', 'researching', 'draft', 'review', 'rejected')",
            name="ck_web_article_candidates_status",
        ),
        CheckConstraint(
            "source_kind IN ('manual', 'seo_import', 'news_handoff')",
            name="ck_web_article_candidates_source_kind",
        ),
        CheckConstraint(
            "search_demand_signal BETWEEN 0 AND 100 AND intent_clarity BETWEEN 0 AND 100 "
            "AND topical_relevance BETWEEN 0 AND 100 AND product_relevance BETWEEN 0 AND 100 "
            "AND audience_usefulness BETWEEN 0 AND 100 AND evergreen_potential BETWEEN 0 AND 100 "
            "AND evidence_availability BETWEEN 0 AND 100 AND existing_content_overlap BETWEEN 0 AND 100 "
            "AND internal_link_potential BETWEEN 0 AND 100 AND risk_review_cost BETWEEN 0 AND 100 "
            "AND freshness_need BETWEEN 0 AND 100 AND news_opportunity BETWEEN 0 AND 100",
            name="ck_web_article_candidate_signals",
        ),
        CheckConstraint("priority_score BETWEEN 0 AND 100", name="ck_web_article_candidate_score"),
        Index("ix_web_article_candidates_queue", "status", "priority_score", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate")
    working_title: Mapped[str] = mapped_column(String(240), nullable=False)
    primary_topic: Mapped[str] = mapped_column(String(64), nullable=False)
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    article_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    search_intent: Mapped[str] = mapped_column(String(24), nullable=False)
    primary_query: Mapped[str] = mapped_column(String(240), nullable=False)
    secondary_queries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    audience: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    evidence_level: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    search_demand_signal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent_clarity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topical_relevance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_relevance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audience_usefulness: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evergreen_potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_availability: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    existing_content_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_link_potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_review_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    freshness_need: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    news_opportunity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    web_article_potential_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WebArticle(Base):
    """Canonical Web article state. Public routes expose only the published status."""

    __tablename__ = "web_articles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'researching', 'draft', 'review', 'approved', 'published', "
            "'update_required', 'archived', 'retracted')",
            name="ck_web_articles_status",
        ),
        CheckConstraint("content_version >= 1", name="ck_web_articles_content_version"),
        CheckConstraint("evergreen_score BETWEEN 0 AND 100", name="ck_web_articles_evergreen"),
        CheckConstraint(
            "product_relevance BETWEEN 0 AND 100", name="ck_web_articles_product_relevance"
        ),
        CheckConstraint(
            "editorial_value BETWEEN 0 AND 100", name="ck_web_articles_editorial_value"
        ),
        Index("ix_web_articles_candidate_id", "candidate_id"),
        Index("ix_web_articles_public_queue", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_article_candidates.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(String(320), nullable=False)
    lead: Mapped[str] = mapped_column(Text, nullable=False)
    body_sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    article_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    search_intent: Mapped[str] = mapped_column(String(24), nullable=False)
    primary_query: Mapped[str] = mapped_column(String(240), nullable=False)
    secondary_queries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(32), nullable=False)
    claims: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    claim_source_matrix: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    author: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    editor: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    domain_reviewer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_slugs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evergreen_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_relevance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    editorial_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    web_article_potential_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    research_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_with_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    research_assistance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correction_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class WebArticleRevision(Base):
    """Immutable snapshot of every submitted or published Web article version."""

    __tablename__ = "web_article_revisions"
    __table_args__ = (
        UniqueConstraint("article_id", "content_version", name="uq_web_article_revision_version"),
        CheckConstraint("content_version >= 1", name="ck_web_article_revision_positive"),
        Index("ix_web_article_revisions_article_created", "article_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey("web_articles.id", ondelete="CASCADE"), nullable=False
    )
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class HermesWebArticleSubmission(Base):
    """Replay-protected receipt for the long-form Hermes boundary."""

    __tablename__ = "hermes_web_article_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'expired')",
            name="ck_hermes_web_article_submissions_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_hermes_web_article_idempotency"),
        UniqueConstraint("request_nonce", name="uq_hermes_web_article_nonce"),
        Index("ix_hermes_web_article_submissions_created", "created_at"),
        Index("ix_hermes_web_article_submissions_expires_status", "expires_at", "status"),
    )

    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("web_article_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    article_id: Mapped[str] = mapped_column(
        ForeignKey("web_articles.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    research_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(64), nullable=False)
    response_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
