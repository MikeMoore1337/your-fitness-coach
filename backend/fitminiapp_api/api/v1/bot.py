import hmac
from typing import Annotated, Literal, cast

import httpx
from fastapi import APIRouter, Header, HTTPException, Path, Request
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import is_valid_timezone
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.notification import NotificationSetting
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.bot import (
    BotDigestDraftRequest,
    BotDigestIssueActionRequest,
    BotDigestIssueActionResponse,
    BotDigestIssueItemResponse,
    BotDigestIssueResponse,
    BotDigestPreferenceRequest,
    BotDigestPreferenceResponse,
    BotNewsModerationRequest,
    BotNewsModerationResponse,
    BotNewsPostActionRequest,
    BotNewsReconcileRequest,
    BotNewsRetryRequest,
    BotNewsRevisionActionRequest,
    BotNewsRevisionActionResponse,
    BotNewsTextEditRequest,
    BotSupportCaseCreateRequest,
    BotSupportCaseCreateResponse,
    BotSupportCaseStatus,
    BotSupportRelayResultRequest,
    BotSupportReplyClaimRequest,
    BotSupportReplyClaimResponse,
    BotSupportReplyResultRequest,
    BotSupportReplyResultResponse,
    BotTelegramLinkRequest,
    BotTelegramLinkResponse,
    BotTimezoneUpdateRequest,
    BotTimezoneUpdateResponse,
)
from fitminiapp_api.services.account_linking import (
    TelegramLinkConflictError,
    TelegramLinkError,
    link_telegram_account,
)
from fitminiapp_api.services.bot_support import (
    SupportRateLimitError,
    claim_support_reply,
    complete_support_reply,
    create_support_case,
    record_support_relay_result,
)
from fitminiapp_api.services.news_editorial import (
    edit_text_revision,
    moderate_draft,
    queue_image_regeneration,
    remove_current_image,
    replace_current_image,
)
from fitminiapp_api.services.news_images import NewsImageError
from fitminiapp_api.services.news_post_management import manage_published_post
from fitminiapp_api.services.news_publication import (
    approve_publication,
    reconcile_uncertain_publication,
    retry_uncertain_publication,
)
from fitminiapp_api.services.password_auth import PasswordAuthError
from fitminiapp_api.services.telegram_auth import (
    get_or_insert_telegram_user,
    normalize_telegram_username,
)
from fitminiapp_api.services.telegram_transport import telegram_transport_options
from fitminiapp_api.services.weekly_digest import (
    DigestIssueView,
    approve_digest_issue,
    close_digest_issue,
    create_digest_draft,
    edit_digest_issue,
    get_digest_preference,
    schedule_digest_issue,
    set_digest_preference,
)

router = APIRouter()
SupportCaseId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
NewsDraftId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def _digest_issue_response(issue: DigestIssueView) -> BotDigestIssueResponse:
    return BotDigestIssueResponse(
        issue_id=issue.issue_id,
        issue_key=issue.issue_key,
        revision=issue.revision,
        status=issue.status,
        rendered_text=issue.rendered_text,
        content_hash=issue.content_hash,
        channel_url=issue.channel_url,
        min_items=issue.min_items,
        scheduled_for_utc=issue.scheduled_for_utc,
        timezone=issue.timezone,
        items=[
            BotDigestIssueItemResponse(
                position=item.position,
                headline=item.headline,
                takeaway=item.takeaway,
                category=item.category,
                channel_permalink=item.channel_permalink,
                requires_owner_review=item.requires_owner_review,
            )
            for item in issue.items
        ],
        blockers=list(issue.blockers),
    )


def _check_bot_token(x_bot_token: str | None) -> None:
    expected = settings.bot_internal_token
    if not expected:
        raise HTTPException(status_code=503, detail="Bot internal token is not configured")
    if not x_bot_token or not hmac.compare_digest(x_bot_token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


def _check_support_admin(telegram_user_id: int) -> None:
    if telegram_user_id not in settings.admin_telegram_id_set:
        raise HTTPException(status_code=403, detail="Forbidden")


def _get_or_create_user(db: Session, payload: BotTimezoneUpdateRequest) -> User:
    username = normalize_telegram_username(payload.username)
    user = get_or_insert_telegram_user(
        db,
        telegram_user_id=payload.telegram_user_id,
        username=username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        photo_url=None,
    )
    user = db.query(User).filter(User.id == user.id).with_for_update().one()
    if payload.username is not None:
        user.username = username
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name

    return user


def _ensure_profile_and_settings(db: Session, user: User) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        full_name = (
            " ".join(part for part in [user.first_name, user.last_name] if part).strip()
            or user.username
            or f"User {user.telegram_user_id}"
        )
        profile = UserProfile(user_id=user.id, full_name=full_name)
        db.add(profile)
        db.flush()

    setting = db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
    if not setting:
        db.add(NotificationSetting(user_id=user.id))

    return profile


@router.post("/timezone", response_model=BotTimezoneUpdateResponse)
def update_timezone_from_bot(
    payload: BotTimezoneUpdateRequest,
    x_bot_token: str | None = Header(default=None),
):
    _check_bot_token(x_bot_token)
    if not is_valid_timezone(payload.timezone):
        raise HTTPException(status_code=400, detail="Unsupported timezone")

    with get_session_context() as db:
        user = _get_or_create_user(db, payload)
        profile = _ensure_profile_and_settings(db, user)
        profile.timezone = payload.timezone
        db.flush()

        return BotTimezoneUpdateResponse(
            telegram_user_id=payload.telegram_user_id,
            timezone=profile.timezone,
        )


@router.post("/link-telegram", response_model=BotTelegramLinkResponse)
def link_telegram_from_bot(
    payload: BotTelegramLinkRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotTelegramLinkResponse:
    _check_bot_token(x_bot_token)
    conflict: TelegramLinkConflictError | None = None
    try:
        with get_session_context() as db:
            try:
                result = link_telegram_account(
                    db,
                    raw_token=payload.token,
                    telegram_user_id=payload.telegram_user_id,
                    username=payload.username,
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                )
            except TelegramLinkConflictError as exc:
                # The token stays consumed even on a conflict, so a leaked link
                # cannot be tried against another Telegram account.
                conflict = exc
                result = None
        if conflict is not None:
            raise HTTPException(status_code=409, detail=str(conflict))
        assert result is not None
        return BotTelegramLinkResponse(status=result.status)
    except PasswordAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TelegramLinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/digest/preference", response_model=BotDigestPreferenceResponse)
def digest_preference_from_bot(
    payload: BotDigestPreferenceRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotDigestPreferenceResponse:
    _check_bot_token(x_bot_token)
    if (
        payload.enabled is True
        and payload.consent_version != settings.weekly_digest_consent_version
    ):
        raise HTTPException(status_code=409, detail="Digest consent version mismatch")
    with get_session_context() as db:
        preference = (
            get_digest_preference(db, telegram_user_id=payload.telegram_user_id)
            if payload.enabled is None
            else set_digest_preference(
                db,
                telegram_user_id=payload.telegram_user_id,
                enabled=payload.enabled,
                presented_consent_version=payload.consent_version,
                username=payload.username,
                first_name=payload.first_name,
                last_name=payload.last_name,
            )
        )
        return BotDigestPreferenceResponse(
            enabled=preference.enabled,
            consent_version=preference.consent_version,
            subscribed_at=preference.subscribed_at,
        )


@router.post("/digest/issues/draft", response_model=BotDigestIssueResponse)
def create_digest_draft_from_bot(
    payload: BotDigestDraftRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotDigestIssueResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        issue = create_digest_draft(
            db,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            min_items=payload.min_items,
        )
        return _digest_issue_response(issue)


@router.post(
    "/digest/issues/{issue_id}/actions",
    response_model=BotDigestIssueActionResponse,
)
def act_on_digest_issue_from_bot(
    issue_id: NewsDraftId,
    payload: BotDigestIssueActionRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotDigestIssueActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        if payload.action in {"remove", "move_up", "move_down", "edit_intro", "edit_item"}:
            result = edit_digest_issue(
                db,
                issue_id=issue_id,
                admin_telegram_user_id=payload.admin_telegram_user_id,
                expected_content_hash=payload.expected_content_hash,
                action=payload.action,
                position=payload.position,
                text_value=payload.text,
            )
        elif payload.action == "approve":
            result = approve_digest_issue(
                db,
                issue_id=issue_id,
                admin_telegram_user_id=payload.admin_telegram_user_id,
                expected_content_hash=payload.expected_content_hash,
            )
        elif payload.action == "schedule":
            if payload.scheduled_local is None or payload.timezone is None:
                raise HTTPException(status_code=422, detail="Schedule and timezone are required")
            result = schedule_digest_issue(
                db,
                issue_id=issue_id,
                admin_telegram_user_id=payload.admin_telegram_user_id,
                expected_content_hash=payload.expected_content_hash,
                scheduled_local=payload.scheduled_local,
                timezone_name=payload.timezone,
            )
        else:
            result = close_digest_issue(
                db,
                issue_id=issue_id,
                admin_telegram_user_id=payload.admin_telegram_user_id,
                expected_content_hash=payload.expected_content_hash,
                action=cast(Literal["cancel", "reject"], payload.action),
            )
        return BotDigestIssueActionResponse(
            status=result.status,
            issue=_digest_issue_response(result.issue) if result.issue is not None else None,
        )


@router.post("/support/cases", response_model=BotSupportCaseCreateResponse)
def create_support_case_from_bot(
    payload: BotSupportCaseCreateRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotSupportCaseCreateResponse:
    _check_bot_token(x_bot_token)
    try:
        with get_session_context() as db:
            result = create_support_case(
                db,
                telegram_user_id=payload.telegram_user_id,
                request_message_id=payload.request_message_id,
                category=payload.category,
            )
            return BotSupportCaseCreateResponse(
                case_id=result.case.id,
                status="created" if result.created else "duplicate",
                case_status=cast(BotSupportCaseStatus, result.case.status),
            )
    except SupportRateLimitError as exc:
        raise HTTPException(status_code=429, detail="Too many support requests") from exc


@router.post("/support/cases/{case_id}/relay-result")
def update_support_relay_result_from_bot(
    case_id: SupportCaseId,
    payload: BotSupportRelayResultRequest,
    x_bot_token: str | None = Header(default=None),
) -> dict[str, str]:
    _check_bot_token(x_bot_token)
    with get_session_context() as db:
        case = record_support_relay_result(db, case_id=case_id, delivered=payload.delivered)
        if case is None:
            raise HTTPException(status_code=404, detail="Support case not found")
        return {"status": case.status}


@router.post(
    "/support/cases/{case_id}/reply-claim",
    response_model=BotSupportReplyClaimResponse,
)
def claim_support_reply_from_bot(
    case_id: SupportCaseId,
    payload: BotSupportReplyClaimRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotSupportReplyClaimResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        claim = claim_support_reply(
            db,
            case_id=case_id,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            reply_message_id=payload.reply_message_id,
        )
        return BotSupportReplyClaimResponse(
            status=claim.status,
            telegram_user_id=claim.telegram_user_id,
        )


@router.post(
    "/support/cases/{case_id}/reply-result",
    response_model=BotSupportReplyResultResponse,
)
def complete_support_reply_from_bot(
    case_id: SupportCaseId,
    payload: BotSupportReplyResultRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotSupportReplyResultResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        recorded = complete_support_reply(
            db,
            case_id=case_id,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            reply_message_id=payload.reply_message_id,
            outcome=payload.outcome,
        )
        if not recorded:
            raise HTTPException(status_code=409, detail="Support reply is not claimable")
        return BotSupportReplyResultResponse(status="recorded")


@router.post(
    "/news/drafts/{draft_id}/moderate",
    response_model=BotNewsModerationResponse,
)
def moderate_news_draft_from_bot(
    draft_id: NewsDraftId,
    payload: BotNewsModerationRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsModerationResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        result = moderate_draft(
            db,
            draft_id=draft_id,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            action=payload.action,
        )
        return BotNewsModerationResponse(
            status=result.status,
            cluster_status=result.cluster_status,
        )


@router.post(
    "/news/drafts/{draft_id}/actions",
    response_model=BotNewsRevisionActionResponse,
)
def act_on_news_revision_from_bot(
    draft_id: NewsDraftId,
    payload: BotNewsRevisionActionRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        if payload.action == "regenerate_image":
            result = queue_image_regeneration(
                db,
                draft_id=draft_id,
                expected_image_revision=payload.expected_image_revision,
                admin_telegram_user_id=payload.admin_telegram_user_id,
            )
            return BotNewsRevisionActionResponse(
                status=result.status, cluster_status=result.cluster_status
            )
        if payload.action == "remove_image":
            result = remove_current_image(
                db,
                draft_id=draft_id,
                expected_image_revision=payload.expected_image_revision,
                admin_telegram_user_id=payload.admin_telegram_user_id,
            )
            return BotNewsRevisionActionResponse(
                status=result.status, cluster_status=result.cluster_status
            )
        approval = approve_publication(
            db,
            draft_id=draft_id,
            expected_image_revision=payload.expected_image_revision,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            mode="immediate" if payload.action == "publish" else "scheduled",
            scheduled_local=payload.scheduled_local,
            timezone_name=payload.timezone,
            urgent_override=payload.urgent_override,
            expected_artifact_hash=payload.expected_artifact_hash or "",
        )
        return BotNewsRevisionActionResponse(
            status=approval.status,
            snapshot_id=approval.snapshot_id,
            blockers=list(approval.blockers),
        )


@router.post(
    "/news/drafts/{draft_id}/text",
    response_model=BotNewsRevisionActionResponse,
)
def edit_news_text_from_bot(
    draft_id: NewsDraftId,
    payload: BotNewsTextEditRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        result = edit_text_revision(
            db,
            draft_id=draft_id,
            expected_image_revision=payload.expected_image_revision,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            draft_text=payload.draft_text,
        )
        return BotNewsRevisionActionResponse(
            status=result.status, cluster_status=result.cluster_status
        )


@router.post(
    "/news/drafts/{draft_id}/image",
    response_model=BotNewsRevisionActionResponse,
)
async def replace_news_image_from_bot(
    draft_id: NewsDraftId,
    request: Request,
    x_bot_token: str | None = Header(default=None),
    x_admin_telegram_user_id: int = Header(..., ge=1),
    x_expected_image_revision: int = Header(..., ge=0),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(x_admin_telegram_user_id)
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > settings.news_image_upload_max_bytes:
            raise HTTPException(status_code=413, detail="image_size_invalid")
        chunks.append(chunk)
    image_data = b"".join(chunks)
    try:
        with get_session_context() as db:
            result = replace_current_image(
                db,
                draft_id=draft_id,
                expected_image_revision=x_expected_image_revision,
                admin_telegram_user_id=x_admin_telegram_user_id,
                image_data=image_data,
            )
            return BotNewsRevisionActionResponse(
                status=result.status, cluster_status=result.cluster_status
            )
    except NewsImageError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc


@router.post(
    "/news/publications/{snapshot_id}/post-action",
    response_model=BotNewsRevisionActionResponse,
)
async def manage_published_news_from_bot(
    snapshot_id: NewsDraftId,
    payload: BotNewsPostActionRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    async with httpx.AsyncClient(timeout=15, **telegram_transport_options()) as client:
        with get_session_context() as db:
            result = await manage_published_post(
                db,
                snapshot_id=snapshot_id,
                admin_telegram_user_id=payload.admin_telegram_user_id,
                action=payload.action,
                text=payload.text,
                client=client,
            )
            return BotNewsRevisionActionResponse(status=result.status)


@router.post(
    "/news/publications/{snapshot_id}/reconcile",
    response_model=BotNewsRevisionActionResponse,
)
def reconcile_news_publication_from_bot(
    snapshot_id: NewsDraftId,
    payload: BotNewsReconcileRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        reconciled = reconcile_uncertain_publication(
            db,
            snapshot_id=snapshot_id,
            admin_telegram_user_id=payload.admin_telegram_user_id,
            channel_message_id=payload.channel_message_id,
        )
        return BotNewsRevisionActionResponse(status="updated" if reconciled else "stale")


@router.post(
    "/news/publications/{snapshot_id}/retry",
    response_model=BotNewsRevisionActionResponse,
)
def retry_news_publication_from_bot(
    snapshot_id: NewsDraftId,
    payload: BotNewsRetryRequest,
    x_bot_token: str | None = Header(default=None),
) -> BotNewsRevisionActionResponse:
    _check_bot_token(x_bot_token)
    _check_support_admin(payload.admin_telegram_user_id)
    with get_session_context() as db:
        retry_status = retry_uncertain_publication(
            db,
            snapshot_id=snapshot_id,
            admin_telegram_user_id=payload.admin_telegram_user_id,
        )
        return BotNewsRevisionActionResponse(status=retry_status)
