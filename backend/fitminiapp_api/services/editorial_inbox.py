"""Read-only editorial inbox for verified Root owners.

Hermes and background workers never receive these endpoints or a publication action.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fitminiapp_api.models.news import WebArticle, WebArticleRevision
from fitminiapp_api.schemas.articles import OwnerArticleReviewDetail, OwnerArticleReviewRow

INBOX_STATUSES = ("draft", "review", "update_required")


def _latest_revision(
    db: Session, article: WebArticle
) -> WebArticleRevision | None:
    return (
        db.query(WebArticleRevision)
        .filter(
            WebArticleRevision.article_id == article.id,
            WebArticleRevision.content_version == article.content_version,
        )
        .one_or_none()
    )


def _blockers(revision: WebArticleRevision | None) -> list[str]:
    if revision is None:
        return ["revision_missing"]
    snapshot = revision.snapshot
    if not isinstance(snapshot, dict):
        return ["revision_invalid"]
    metadata = snapshot.get("metadata")
    if not isinstance(metadata, dict):
        return ["revision_metadata_missing"]
    blockers = metadata.get("review_blockers")
    if not isinstance(blockers, list) or any(not isinstance(x, str) for x in blockers):
        return ["revision_blockers_missing"]
    return blockers


def _row(article: WebArticle, revision: WebArticleRevision | None) -> OwnerArticleReviewRow:
    matrix = article.claim_source_matrix if isinstance(article.claim_source_matrix, list) else []
    return OwnerArticleReviewRow(
        article_id=article.id,
        candidate_id=article.candidate_id,
        slug=article.slug,
        title=article.title,
        article_status=article.status,
        content_version=article.content_version,
        content_hash=article.content_hash,
        risk_level=article.risk_level,
        evidence_level=article.evidence_level,
        source_count=len(article.sources),
        claim_count=len(article.claims),
        pending_claim_count=sum(
            1
            for item in matrix
            if isinstance(item, dict) and item.get("review_status") != "verified"
        ),
        review_blockers=_blockers(revision),
        generated_with_ai=article.generated_with_ai,
        research_version=article.research_version,
        updated_at=article.updated_at,
    )


def list_root_article_drafts(
    db: Session, *, limit: int, offset: int
) -> list[OwnerArticleReviewRow]:
    """Bounded read. No state transition, publication flag, or implicit approval."""
    articles = (
        db.query(WebArticle)
        .filter(WebArticle.status.in_(INBOX_STATUSES))
        .order_by(WebArticle.created_at.desc(), WebArticle.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    if not articles:
        return []
    revision_keys = {
        (article.id, article.content_version) for article in articles
    }
    revisions = (
        db.query(WebArticleRevision)
        .filter(WebArticleRevision.article_id.in_([article.id for article in articles]))
        .all()
    )
    selected = {
        (revision.article_id, revision.content_version): revision
        for revision in revisions
        if (revision.article_id, revision.content_version) in revision_keys
    }
    return [_row(article, selected.get((article.id, article.content_version))) for article in articles]


def get_root_article_draft(
    db: Session, article_id: str
) -> OwnerArticleReviewDetail | None:
    """Show exact persisted source evidence, never fabricated verification."""
    article = db.get(WebArticle, article_id)
    if article is None or article.status not in INBOX_STATUSES:
        return None
    row = _row(article, _latest_revision(db, article))
    return OwnerArticleReviewDetail(
        **row.model_dump(),
        description=article.description,
        lead=article.lead,
        body_sections=article.body_sections,
        topics=article.topics,
        claims=article.claims,
        sources=article.sources,
        claim_source_matrix=article.claim_source_matrix,
        domain_reviewer=article.domain_reviewer,
        provider=article.provider,
        model=article.model,
        prompt_version=article.prompt_version,
        skill_version=article.skill_version,
    )
