from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.api.dependencies.auth import require_root_admin
from fitminiapp_api.db.session import get_db, get_session_context
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.admin import (
    AdminAuditRow,
    AdminFunnelResponse,
    AdminJobRow,
    AdminOperationRequest,
    AdminTrainerCapabilityUpdate,
    AdminTrainerCapacityResponse,
    AdminUserDetail,
    AdminUserSearchRow,
    AdminUserStatusUpdate,
)
from fitminiapp_api.schemas.articles import (
    OwnerArticleReviewDetail,
    OwnerArticleReviewRow,
    OwnerExistingDraftPublishRequest,
    OwnerWebArticlePublishRequest,
    OwnerWebArticlePublishResponse,
)
from fitminiapp_api.services.admin_operations import (
    end_relationship,
    funnel_aggregates,
    list_audit_events,
    list_jobs,
    retry_account_export,
    search_users,
    trainer_capacity_aggregates,
    update_trainer_capability,
    update_user_status,
    user_detail,
)
from fitminiapp_api.services.editorial_inbox import (
    get_root_article_draft,
    list_root_article_drafts,
)
from fitminiapp_api.services.web_articles import (
    WebArticleError,
    publish_existing_owner_article,
    publish_owner_web_article,
)

router = APIRouter()


@router.get("/users", response_model=list[AdminUserSearchRow])
def admin_users(
    q: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return search_users(db, q)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> dict:
    return user_detail(db, user_id)


@router.patch("/users/{user_id}/status", response_model=AdminUserDetail)
def admin_update_user_status(
    user_id: int,
    payload: AdminUserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return update_user_status(
        db,
        actor=current_user,
        target_user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
    )


@router.patch("/users/{user_id}/trainer-capability", response_model=AdminUserDetail)
def admin_update_trainer_capability(
    user_id: int,
    payload: AdminTrainerCapabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return update_trainer_capability(
        db,
        actor=current_user,
        target_user_id=user_id,
        is_active=payload.is_active,
        reason=payload.reason,
    )


@router.post("/relationships/{relationship_id}/end", response_model=AdminUserDetail)
def admin_end_relationship(
    relationship_id: int,
    payload: AdminOperationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return end_relationship(
        db,
        actor=current_user,
        relationship_id=relationship_id,
        reason=payload.reason,
    )


@router.get("/jobs", response_model=list[AdminJobRow])
def admin_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return list_jobs(db, limit=limit)


@router.post("/exports/{export_id}/retry", response_model=AdminJobRow)
def admin_retry_export(
    export_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root_admin),
) -> dict:
    return retry_account_export(db, actor=current_user, export_id=export_id)


@router.get("/funnel", response_model=AdminFunnelResponse)
def admin_funnel(
    period_days: int = Query(default=30, ge=7, le=730),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> dict:
    return funnel_aggregates(db, period_days=period_days)


@router.get("/trainer-capacity", response_model=AdminTrainerCapacityResponse)
def admin_trainer_capacity(
    period_days: int = Query(default=30, ge=7, le=730),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> dict:
    return trainer_capacity_aggregates(db, period_days=period_days)


@router.get("/audit", response_model=list[AdminAuditRow])
def admin_audit(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[dict]:
    return list_audit_events(db, limit=limit)


@router.get("/articles/drafts", response_model=list[OwnerArticleReviewRow])
def admin_article_drafts(
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> list[OwnerArticleReviewRow]:
    """Root-only read: no approval or publication side effects."""
    return list_root_article_drafts(db, limit=limit, offset=offset)


@router.get("/articles/drafts/{article_id}", response_model=OwnerArticleReviewDetail)
def admin_article_draft_detail(
    article_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_root_admin),
) -> OwnerArticleReviewDetail:
    """Owner inspection of exact draft evidence, including pending claims."""
    if len(article_id) != 32 or any(ch not in "0123456789abcdef" for ch in article_id):
        raise HTTPException(status_code=404, detail="article_not_found")
    result = get_root_article_draft(db, article_id)
    if result is None:
        raise HTTPException(status_code=404, detail="article_not_found")
    return result


@router.post("/articles/drafts/publish", response_model=OwnerWebArticlePublishResponse)
def admin_publish_existing_article(
    payload: OwnerExistingDraftPublishRequest,
    current_user: User = Depends(require_root_admin),
) -> OwnerWebArticlePublishResponse:
    """Root-only explicit confirmation of an exact existing draft revision."""
    try:
        with get_session_context() as db:
            article = publish_existing_owner_article(
                db,
                article_id=payload.article_id,
                expected_content_hash=payload.expected_content_hash,
                expected_content_version=payload.expected_content_version,
                actor_user_id=current_user.id,
            )
            return OwnerWebArticlePublishResponse(
                article_id=article.id,
                slug=article.slug,
                article_status="published",
                content_version=article.content_version,
                canonical_url=article.canonical_url,
                editorial_decision="root_owner_publication",
                scientific_verification="not_attested",
            )
    except WebArticleError as exc:
        if exc.code == "article_not_found":
            raise HTTPException(status_code=404, detail=exc.code) from exc
        if exc.code == "article_revision_conflict":
            raise HTTPException(status_code=409, detail=exc.code) from exc
        raise HTTPException(status_code=422, detail=exc.code) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="article_conflict") from exc


@router.post("/articles/publish", response_model=OwnerWebArticlePublishResponse)
def admin_publish_web_article(
    payload: OwnerWebArticlePublishRequest,
    current_user: User = Depends(require_root_admin),
) -> OwnerWebArticlePublishResponse:
    """One explicit Root decision; Hermes intake and expert-review statuses remain untouched."""
    try:
        with get_session_context() as db:
            article = publish_owner_web_article(
                db,
                payload.article,
                actor_user_id=current_user.id,
                generated_with_ai=payload.generated_with_ai,
            )
            response = OwnerWebArticlePublishResponse(
                article_id=article.id,
                slug=article.slug,
                article_status="published",
                content_version=article.content_version,
                canonical_url=article.canonical_url,
                editorial_decision="root_owner_publication",
                scientific_verification="not_attested",
            )
        return response
    except WebArticleError as exc:
        if exc.code == "slug_conflict":
            raise HTTPException(status_code=409, detail=exc.code) from exc
        raise HTTPException(status_code=422, detail=exc.code) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="article_conflict") from exc
