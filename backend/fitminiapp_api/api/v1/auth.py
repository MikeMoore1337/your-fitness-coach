import logging
from datetime import UTC, timedelta
from typing import Any
from uuid import uuid4

from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from httpx import HTTPError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.auth_identity import AuthIdentity, LocalCredential
from fitminiapp_api.models.notification import NotificationSetting
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.auth import (
    AuthTokenRequest,
    DevLoginRequest,
    EmailLoginRequest,
    EmailRegisterRequest,
    EmailRequest,
    MessageResponse,
    PasswordResetConfirmRequest,
    RefreshRequest,
    RegistrationResponse,
    TelegramInitRequest,
    TokenPairResponse,
)
from fitminiapp_api.services.account_linking import (
    OAUTH_LINK_PROVIDERS,
    OAuthLinkConflictError,
    OAuthLinkError,
    link_oauth_account,
    oauth_link_purpose,
)
from fitminiapp_api.services.audit import record_audit_event
from fitminiapp_api.services.auth_email import password_reset_email, verification_email
from fitminiapp_api.services.auth_identities import ensure_auth_identity, ensure_telegram_identity
from fitminiapp_api.services.auth_redirects import auth_error_redirect, safe_auth_next_path
from fitminiapp_api.services.jwt import (
    AuthError,
    build_access_token,
    build_refresh_token,
    decode_token,
    extract_bearer_token,
)
from fitminiapp_api.services.oauth_login import (
    VK_SESSION_KEY,
    OAuthAccountBlockedError,
    OAuthProviderResponseError,
    OAuthStateError,
    configured_oauth_client,
    get_or_create_oauth_user,
    merge_vk_callback_payload,
)
from fitminiapp_api.services.oauth_transactions import (
    OAUTH_BROWSER_MARKER_KEY,
    authlib_state_data,
    browser_marker_from_session,
    claim_oauth_transaction,
    create_oauth_transaction,
    finish_oauth_transaction,
    has_pending_oauth_transactions,
    is_valid_oauth_state,
    prepare_oauth_session,
    scrub_legacy_oauth_session,
    transaction_hash_prefix,
)
from fitminiapp_api.services.password_auth import (
    PasswordAuthError,
    authenticate_local_user,
    consume_action_token,
    create_action_token,
    hash_password,
    local_identity_by_email,
    utcnow,
    validate_action_token,
)
from fitminiapp_api.services.telegram_auth import (
    get_or_create_user_from_init_data,
    normalize_telegram_username,
    validate_telegram_init_data,
)
from fitminiapp_api.services.token_service import (
    consume_refresh_token,
    get_refresh_token_by_jti,
    is_refresh_token_valid,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token_family,
    save_refresh_token,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_web_auth() -> None:
    if not settings.enable_web_auth:
        raise HTTPException(status_code=404, detail="Web-авторизация отключена")


def _require_email_auth() -> None:
    if not settings.enable_email_auth:
        raise HTTPException(status_code=404, detail="Авторизация по email отключена")


def _development_action_token(raw_token: str) -> str | None:
    return raw_token if settings.app_env in {"dev", "test"} else None


def _send_auth_message(sender, email: str, raw_token: str) -> None:
    try:
        delivered = sender(email, raw_token)
    except Exception as exc:
        logger.error("auth_email_delivery_failed", exc_info=exc)
        delivered = False
    if not delivered and settings.app_env == "prod":
        raise HTTPException(
            status_code=503,
            detail="Аккаунт сохранён, но письмо пока не отправлено. Повторите отправку позже.",
        )


def _oauth_callback_url(provider: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/api/v1/auth/oauth/{provider}/callback"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/api/v1/auth",
        secure=settings.app_env == "prod",
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"


def _safe_next_path(value: str | None) -> str | None:
    return safe_auth_next_path(value)


def _clear_oauth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.oauth_session_cookie_name,
        path="/",
        secure=settings.app_env == "prod",
        httponly=True,
        samesite="none" if settings.app_env == "prod" else "lax",
    )


def _log_oauth_event(
    event: str,
    request: Request,
    *,
    provider: str,
    purpose: str,
    reason: str,
    state: str | None = None,
) -> None:
    extra: dict[str, str] = {
        "provider": provider,
        "purpose": purpose,
        "reason": reason,
    }
    if state and is_valid_oauth_state(state):
        extra["transaction_hash_prefix"] = transaction_hash_prefix(state)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        extra["request_id"] = request_id
    logger.warning(event, extra=extra)


def _cleanup_oauth_artifact(
    request: Request,
    response: Response,
    db: Session,
    *,
    browser_marker: str | None,
) -> None:
    scrub_legacy_oauth_session(request.session)
    if has_pending_oauth_transactions(db, browser_marker):
        return
    request.session.pop(OAUTH_BROWSER_MARKER_KEY, None)

    # SessionMiddleware turns a bad or expired signed cookie into an empty
    # session. Explicitly remove that cookie once no OAuth attempt remains.
    if not request.session and request.cookies.get(settings.oauth_session_cookie_name):
        _clear_oauth_cookie(response)


def _oauth_error_code(provider_error: str) -> str:
    return (
        "denied"
        if provider_error in {"access_denied", "cancelled", "user_cancelled", "user_denied"}
        else "invalid_state"
        if provider_error in {"invalid_state", "mismatching_state", "missing_state"}
        else "provider_failure"
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
        secure=settings.app_env == "prod",
        httponly=True,
        samesite="strict",
    )


def _refresh_session_error(status_code: int, detail: str) -> HTTPException:
    cookie_response = Response()
    _clear_refresh_cookie(cookie_response)
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={
            "Set-Cookie": cookie_response.headers["set-cookie"],
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
        },
    )


def issue_token_pair(
    db: Session,
    user: User,
    response: Response,
    *,
    commit: bool = True,
    session_family_id: str | None = None,
) -> TokenPairResponse:
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")

    family_id = session_family_id or uuid4().hex
    access_token, _, _ = build_access_token(user.id, session_family_id=family_id)
    refresh_token, refresh_jti, refresh_expires_at = build_refresh_token(
        user.id,
        session_family_id=family_id,
    )

    save_refresh_token(
        db,
        user_id=user.id,
        jti=refresh_jti,
        family_id=family_id,
        raw_token=refresh_token,
        expires_at=refresh_expires_at,
        commit=commit,
    )
    _set_refresh_cookie(response, refresh_token)

    return TokenPairResponse(
        access_token=access_token,
    )


def _active_refresh_session(request: Request, db: Session) -> tuple[User, str]:
    raw_token = request.cookies.get(settings.refresh_cookie_name, "")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Требуется активная сессия")
    try:
        payload = decode_token(raw_token, expected_type="refresh")
    except AuthError:
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")
    raw_user_id = payload.get("sub")
    if not isinstance(raw_user_id, str):
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")
    try:
        user_id = int(raw_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")

    jti = payload.get("jti")
    family_id = payload.get("sid")
    if not isinstance(jti, str) or not isinstance(family_id, str) or not family_id:
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")
    row = get_refresh_token_by_jti(db, jti)
    if (
        row is None
        or row.user_id != user_id
        or row.family_id != family_id
        or not is_refresh_token_valid(row, raw_token)
    ):
        raise HTTPException(status_code=401, detail="Сессия недействительна или истекла")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    return user, family_id


@router.post("/telegram/init", response_model=TokenPairResponse)
@limiter.limit("20/minute")
def telegram_init_auth(
    request: Request,
    response: Response,
    payload: TelegramInitRequest,
    db: Session = Depends(get_db),
):
    init_data = payload.init_data.strip()
    if not init_data:
        raise HTTPException(status_code=400, detail="init_data is required")

    bot_token = settings.telegram_bot_token
    if not bot_token or bot_token == "replace-me":
        raise HTTPException(status_code=500, detail="Telegram bot token is not configured")

    try:
        validated_init_data = validate_telegram_init_data(
            init_data,
            bot_token,
            max_age_seconds=settings.telegram_init_data_max_age_seconds,
        )
    except ValueError as exc:
        logger.warning("telegram_auth_rejected", extra={"reason": type(exc).__name__})
        raise HTTPException(
            status_code=401,
            detail="Данные Telegram недействительны или истекли",
        ) from exc

    user = get_or_create_user_from_init_data(db, validated_init_data)
    return issue_token_pair(db, user, response)


@router.get("/oauth/{provider}/start")
@limiter.limit("20/minute")
async def oauth_start(
    request: Request,
    provider: str,
    next: str | None = None,
    db: Session = Depends(get_db),
):
    _require_web_auth()
    normalized_provider = provider.strip().lower()
    client = configured_oauth_client(normalized_provider)
    if client is None:
        return RedirectResponse(
            url=auth_error_redirect("unavailable", next_path=next), status_code=303
        )
    next_path = _safe_next_path(next)
    browser_marker = prepare_oauth_session(request.session)
    try:
        callback_url = _oauth_callback_url(normalized_provider)
        authorization_data = await _create_authorization_data(
            client,
            normalized_provider,
            callback_url,
        )
        create_oauth_transaction(
            db=db,
            browser_marker=browser_marker,
            provider=normalized_provider,
            purpose="login",
            authorization_data=authorization_data,
            next_path=next_path,
        )
    except HTTPError, OAuthError, IntegrityError, RuntimeError, ValueError:
        db.rollback()
        _log_oauth_event(
            "oauth_start_failed",
            request,
            provider=normalized_provider,
            purpose="login",
            reason="provider_failure",
        )
        response = RedirectResponse(
            auth_error_redirect(
                "unavailable",
                next_path=next_path,
                provider=normalized_provider,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response

    return RedirectResponse(authorization_data["url"], status_code=302)


@router.get("/oauth/{provider}/link/start")
@limiter.limit("20/minute")
async def oauth_link_start(
    request: Request,
    provider: str,
    token: str,
    db: Session = Depends(get_db),
):
    _require_web_auth()
    normalized_provider = provider.strip().lower()
    if normalized_provider not in OAUTH_LINK_PROVIDERS:
        raise HTTPException(status_code=404, detail="Провайдер входа не настроен")
    client = configured_oauth_client(normalized_provider)
    if client is None:
        raise HTTPException(status_code=404, detail="Провайдер входа не настроен")
    try:
        action_token = validate_action_token(
            db,
            token,
            purpose=oauth_link_purpose(normalized_provider),
        )
    except (PasswordAuthError, OAuthLinkError) as exc:
        raise HTTPException(status_code=400, detail="Ссылка привязки недействительна") from exc
    target = db.query(User).filter(User.id == action_token.user_id).first()
    if target is None or not target.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    session_user, session_family_id = _active_refresh_session(request, db)
    if (
        session_user.id != target.id
        or action_token.session_family_id is None
        or action_token.session_family_id != session_family_id
    ):
        record_audit_event(
            db,
            action="account.oauth_link_session_mismatch",
            resource_type="user",
            actor_user_id=session_user.id,
            target_user_id=target.id,
            resource_id=target.id,
            details={"provider": normalized_provider},
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Ссылка создана в другой сессии")
    browser_marker = prepare_oauth_session(request.session)
    try:
        callback_url = _oauth_callback_url(normalized_provider)
        authorization_data = await _create_authorization_data(
            client,
            normalized_provider,
            callback_url,
        )
        create_oauth_transaction(
            db,
            browser_marker=browser_marker,
            provider=normalized_provider,
            purpose="link",
            authorization_data=authorization_data,
            link_action_token_hash=action_token.token_hash,
            link_user_id=target.id,
            session_family_id=session_family_id,
        )
    except HTTPError, OAuthError, IntegrityError, RuntimeError, ValueError:
        db.rollback()
        _log_oauth_event(
            "oauth_link_start_failed",
            request,
            provider=normalized_provider,
            purpose="link",
            reason="provider_failure",
        )
        response = RedirectResponse(
            auth_error_redirect("unavailable", provider=normalized_provider, link=True),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response

    return RedirectResponse(authorization_data["url"], status_code=302)


async def _create_authorization_data(
    client: Any,
    provider: str,
    redirect_uri: str,
) -> dict[str, Any]:
    if provider == "vk":
        data = client.create_authorization_data(redirect_uri)
    else:
        data = await client.create_authorization_url(redirect_uri)
    if not isinstance(data, dict) or not isinstance(data.get("url"), str):
        raise ValueError("OAuth provider returned invalid authorization data")
    result = dict(data)
    result["redirect_uri"] = redirect_uri
    return result


def _add_callback_param(params: dict[str, str], key: str, value: object) -> None:
    normalized = str(value)
    existing = params.get(key)
    if existing is not None and existing != normalized:
        raise ValueError("OAuth callback contains conflicting parameters")
    params[key] = normalized


async def _oauth_callback_params(request: Request, provider: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for query_key, query_value in request.query_params.multi_items():
        _add_callback_param(params, query_key, query_value)
    if request.scope.get("method", "GET") != "GET":
        async with request.form() as form:
            for form_key, form_value in form.multi_items():
                _add_callback_param(params, form_key, form_value)
    if provider == "vk":
        return merge_vk_callback_payload(params)
    return params


def _set_temporary_authlib_state(
    request: Request,
    client: Any,
    provider: str,
    row,
) -> None:
    state_payload = authlib_state_data(row)
    if provider == "vk":
        request.session[VK_SESSION_KEY] = {
            "state": row.state,
            "code_verifier": row.code_verifier,
            "redirect_uri": row.redirect_uri,
        }
        return
    client_name = getattr(client, "name", None) or provider
    request.session[f"_state_{client_name}_{row.state}"] = {
        "data": state_payload,
        "exp": row.expires_at.replace(tzinfo=UTC).timestamp(),
    }


async def _oauth_callback_impl(
    request: Request,
    provider: str,
    db: Session,
) -> Response:
    _require_web_auth()
    normalized_provider = provider.strip().lower()
    client = configured_oauth_client(normalized_provider)
    if client is None:
        raise HTTPException(status_code=404, detail="Провайдер входа не настроен")
    browser_marker = browser_marker_from_session(request.session)
    try:
        params = await _oauth_callback_params(request, normalized_provider)
    except ValueError, RuntimeError:
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose="login",
            reason="malformed_session",
        )
        response = RedirectResponse(
            auth_error_redirect("invalid_state", provider=normalized_provider),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response

    state = params.get("state")
    claim = claim_oauth_transaction(
        db,
        browser_marker=browser_marker,
        provider=normalized_provider,
        state=state,
    )
    row = claim.transaction
    if claim.reason is not None or row is None:
        purpose = row.purpose if row is not None else "login"
        is_link = purpose == "link"
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=purpose,
            reason=claim.reason or "invalid_state",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "invalid_state",
                next_path=row.next_path if row is not None and not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response

    is_link = row.purpose == "link"
    try:
        provider_error = params.get("error")
        if provider_error:
            code = _oauth_error_code(provider_error)
            failure_reason = "provider_denied" if code == "denied" else "provider_failure"
            finish_oauth_transaction(db, row, failure_reason=failure_reason)
            _log_oauth_event(
                "oauth_link_failed" if is_link else "oauth_login_failed",
                request,
                provider=normalized_provider,
                purpose=row.purpose,
                reason=failure_reason,
                state=state,
            )
            response = RedirectResponse(
                auth_error_redirect(
                    code,
                    next_path=row.next_path,
                    provider=normalized_provider,
                    link=is_link,
                ),
                status_code=303,
            )
            _cleanup_oauth_artifact(
                request,
                response,
                db,
                browser_marker=browser_marker,
            )
            return response

        _set_temporary_authlib_state(request, client, normalized_provider, row)
        request.state.oauth_callback_params = params
        token = await client.authorize_access_token(request)
        if not isinstance(token, dict):
            raise ValueError("OAuth provider returned an invalid token response")
        if normalized_provider == "yandex":
            profile_response = await client.get("info?format=json", token=token)
            profile_response.raise_for_status()
            raw_claims = profile_response.json()
            if not isinstance(raw_claims, dict):
                raise ValueError("Yandex returned an invalid user profile")
        else:
            userinfo = token.get("userinfo")
            if not isinstance(userinfo, dict):
                raise ValueError("OAuth provider returned invalid identity claims")
            raw_claims = dict(userinfo)
        if is_link:
            if not row.link_action_token_hash or not row.link_user_id or not row.session_family_id:
                raise OAuthLinkError("Сессия привязки недействительна")
            try:
                session_user, session_family_id = _active_refresh_session(request, db)
            except HTTPException as exc:
                raise OAuthLinkError("Сессия привязки недействительна") from exc
            if session_user.id != row.link_user_id or session_family_id != row.session_family_id:
                raise OAuthLinkError("Сессия привязки недействительна")
            try:
                user = link_oauth_account(
                    db,
                    action_token_hash=row.link_action_token_hash,
                    provider=normalized_provider,
                    raw_claims=raw_claims,
                    expected_session_family_id=row.session_family_id,
                )
            except OAuthLinkConflictError:
                db.commit()
                finish_oauth_transaction(db, row, failure_reason="conflict")
                _log_oauth_event(
                    "oauth_link_failed",
                    request,
                    provider=normalized_provider,
                    purpose="link",
                    reason="conflict",
                    state=state,
                )
                response = RedirectResponse(
                    auth_error_redirect(
                        "conflict",
                        provider=normalized_provider,
                        link=True,
                    ),
                    status_code=303,
                )
                _cleanup_oauth_artifact(
                    request,
                    response,
                    db,
                    browser_marker=browser_marker,
                )
                return response
            except OAuthLinkError, PasswordAuthError:
                db.commit()
                finish_oauth_transaction(db, row, failure_reason="invalid_state")
                _log_oauth_event(
                    "oauth_link_failed",
                    request,
                    provider=normalized_provider,
                    purpose="link",
                    reason="invalid_state",
                    state=state,
                )
                response = RedirectResponse(
                    auth_error_redirect(
                        "invalid_state",
                        provider=normalized_provider,
                        link=True,
                    ),
                    status_code=303,
                )
                _cleanup_oauth_artifact(
                    request,
                    response,
                    db,
                    browser_marker=browser_marker,
                )
                return response
            finish_oauth_transaction(db, row, commit=False)
            db.commit()
            response = RedirectResponse(
                url=f"/app?auth_linked={normalized_provider}",
                status_code=303,
            )
            _cleanup_oauth_artifact(
                request,
                response,
                db,
                browser_marker=browser_marker,
            )
            return response
        else:
            user = get_or_create_oauth_user(
                db,
                provider=normalized_provider,
                raw_claims=raw_claims,
            )
        response = RedirectResponse(
            url=row.next_path or "/app",
            status_code=303,
        )
        issue_token_pair(db, user, response, commit=False)
        finish_oauth_transaction(db, row, commit=False)
        db.commit()
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthAccountBlockedError:
        db.rollback()
        finish_oauth_transaction(db, row, failure_reason="blocked")
        _log_oauth_event(
            "oauth_login_blocked",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason="blocked",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "blocked",
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthStateError:
        db.rollback()
        finish_oauth_transaction(db, row, failure_reason="invalid_state")
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason="invalid_state",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "invalid_state",
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthProviderResponseError as exc:
        code = _oauth_error_code(exc.error)
        db.rollback()
        finish_oauth_transaction(
            db,
            row,
            failure_reason="provider_denied" if code == "denied" else "provider_failure",
        )
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason=code,
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                code,
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except MismatchingStateError:
        db.rollback()
        finish_oauth_transaction(db, row, failure_reason="invalid_state")
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason="invalid_state",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "invalid_state",
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthError as exc:
        oauth_error = getattr(exc, "error", "")
        code = _oauth_error_code(oauth_error)
        db.rollback()
        finish_oauth_transaction(
            db,
            row,
            failure_reason="provider_denied" if code == "denied" else "provider_failure",
        )
        _log_oauth_event(
            "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason=code,
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                code,
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthLinkConflictError:
        db.commit()
        finish_oauth_transaction(db, row, failure_reason="conflict")
        response = RedirectResponse(
            auth_error_redirect("conflict", provider=normalized_provider, link=True),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except OAuthLinkError, PasswordAuthError:
        db.commit()
        finish_oauth_transaction(db, row, failure_reason="invalid_state")
        _log_oauth_event(
            "oauth_link_failed" if is_link else "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason="invalid_state",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "invalid_state",
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response
    except HTTPError, IntegrityError, ValueError, RuntimeError:
        db.rollback()
        finish_oauth_transaction(db, row, failure_reason="provider_failure")
        _log_oauth_event(
            "oauth_link_failed" if is_link else "oauth_login_failed",
            request,
            provider=normalized_provider,
            purpose=row.purpose,
            reason="provider_failure",
            state=state,
        )
        response = RedirectResponse(
            auth_error_redirect(
                "provider_failure",
                next_path=row.next_path if not is_link else None,
                provider=normalized_provider,
                link=is_link,
            ),
            status_code=303,
        )
        _cleanup_oauth_artifact(
            request,
            response,
            db,
            browser_marker=browser_marker,
        )
        return response


@router.get(
    "/oauth/{provider}/callback",
    operation_id="oauth_callback_get",
)
@limiter.limit("20/minute")
async def oauth_callback_get(
    request: Request,
    provider: str,
    db: Session = Depends(get_db),
) -> Response:
    return await _oauth_callback_impl(request, provider, db)


@router.post(
    "/oauth/{provider}/callback",
    operation_id="oauth_callback_post",
)
@limiter.limit("20/minute")
async def oauth_callback_post(
    request: Request,
    provider: str,
    db: Session = Depends(get_db),
) -> Response:
    return await _oauth_callback_impl(request, provider, db)


@router.post("/email/register", response_model=RegistrationResponse, status_code=201)
@limiter.limit("5/hour")
def email_register(
    request: Request,
    payload: EmailRegisterRequest,
    db: Session = Depends(get_db),
) -> RegistrationResponse:
    _require_email_auth()
    existing_email = local_identity_by_email(db, payload.email)
    existing_username = (
        db.query(LocalCredential)
        .filter(LocalCredential.username_normalized == payload.username)
        .first()
    )
    if existing_email is not None or existing_username is not None:
        raise HTTPException(status_code=409, detail="Email или имя пользователя уже заняты")

    try:
        user = User(
            telegram_user_id=None,
            username=payload.username,
            is_active=True,
        )
        db.add(user)
        db.flush()
        ensure_auth_identity(
            db,
            user,
            provider="password",
            subject=payload.email,
            email=payload.email,
            email_verified=False,
            mark_login=False,
        )
        db.add(
            LocalCredential(
                user_id=user.id,
                username_normalized=payload.username,
                password_hash=hash_password(payload.password),
            )
        )
        db.add(UserProfile(user_id=user.id, full_name=payload.username))
        db.add(NotificationSetting(user_id=user.id))
        raw_token = create_action_token(
            db,
            user.id,
            purpose="verify_email",
            lifetime=timedelta(hours=24),
        )
        db.commit()
    except PasswordAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Email или имя пользователя уже заняты"
        ) from exc

    _send_auth_message(
        lambda email, token: verification_email(
            email,
            token,
            next_path=payload.next_path,
        ),
        payload.email,
        raw_token,
    )
    return RegistrationResponse(verification_token=_development_action_token(raw_token))


@router.post("/email/verify", response_model=TokenPairResponse)
@limiter.limit("10/hour")
def verify_email(
    request: Request,
    response: Response,
    payload: AuthTokenRequest,
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    _require_email_auth()
    try:
        token = consume_action_token(db, payload.token, purpose="verify_email")
    except PasswordAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    identity = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.user_id == token.user_id, AuthIdentity.provider == "password")
        .first()
    )
    user = db.query(User).filter(User.id == token.user_id).first()
    if identity is None or user is None or not user.is_active:
        db.rollback()
        raise HTTPException(status_code=400, detail="Аккаунт недоступен")
    identity.email_verified = True
    identity.last_login_at = utcnow()
    token_pair = issue_token_pair(db, user, response, commit=False)
    db.commit()
    return token_pair


@router.post("/email/login", response_model=TokenPairResponse)
@limiter.limit("10/minute")
def email_login(
    request: Request,
    response: Response,
    payload: EmailLoginRequest,
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    _require_email_auth()
    try:
        user = authenticate_local_user(db, payload.email, payload.password)
    except PasswordAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return issue_token_pair(db, user, response)


@router.post("/email/verification/resend", response_model=MessageResponse)
@limiter.limit("3/hour")
def resend_verification(
    request: Request,
    payload: EmailRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    _require_email_auth()
    identity = local_identity_by_email(db, payload.email)
    raw_token: str | None = None
    if identity is not None and not identity.email_verified:
        raw_token = create_action_token(
            db,
            identity.user_id,
            purpose="verify_email",
            lifetime=timedelta(hours=24),
        )
        db.commit()
        _send_auth_message(verification_email, payload.email, raw_token)
    return MessageResponse(
        message="Если аккаунт существует, письмо с подтверждением отправлено",
        action_token=_development_action_token(raw_token) if raw_token else None,
    )


@router.post("/password/reset/request", response_model=MessageResponse)
@limiter.limit("3/hour")
def request_password_reset(
    request: Request,
    payload: EmailRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    _require_email_auth()
    identity = local_identity_by_email(db, payload.email)
    raw_token: str | None = None
    if identity is not None and identity.email_verified:
        raw_token = create_action_token(
            db,
            identity.user_id,
            purpose="reset_password",
            lifetime=timedelta(hours=1),
        )
        db.commit()
        _send_auth_message(password_reset_email, payload.email, raw_token)
    return MessageResponse(
        message="Если аккаунт существует, письмо для восстановления отправлено",
        action_token=_development_action_token(raw_token) if raw_token else None,
    )


@router.post("/password/reset/confirm", response_model=MessageResponse)
@limiter.limit("10/hour")
def confirm_password_reset(
    request: Request,
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    _require_email_auth()
    try:
        token = consume_action_token(db, payload.token, purpose="reset_password")
        new_hash = hash_password(payload.password)
    except PasswordAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    credential = db.query(LocalCredential).filter(LocalCredential.user_id == token.user_id).first()
    if credential is None:
        db.rollback()
        raise HTTPException(status_code=400, detail="Аккаунт недоступен")
    credential.password_hash = new_hash
    credential.password_changed_at = utcnow()
    revoke_all_user_refresh_tokens(db, token.user_id, commit=False)
    db.commit()
    return MessageResponse(message="Пароль обновлён. Теперь можно войти.")


@router.post("/dev-login", response_model=TokenPairResponse)
@limiter.limit("30/minute")
def dev_login(
    request: Request,
    response: Response,
    payload: DevLoginRequest,
    db: Session = Depends(get_db),
):
    if not settings.enable_dev_auth:
        raise HTTPException(status_code=403, detail="Dev-вход отключён")

    username = normalize_telegram_username(payload.username) if payload.username else None
    user = db.query(User).filter(User.telegram_user_id == payload.telegram_user_id).first()
    if not user:
        user = User(
            telegram_user_id=payload.telegram_user_id,
            username=username
            if payload.username is not None
            else f"dev_{payload.telegram_user_id}",
            is_coach=payload.is_coach,
            is_admin=payload.is_admin,
            is_active=True,
            measurement_eligibility=("technical" if settings.app_env != "prod" else "real_client"),
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                full_name=payload.full_name,
            )
        )
        db.add(NotificationSetting(user_id=user.id))
    else:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Пользователь заблокирован")

        user.is_coach = payload.is_coach
        user.is_admin = payload.is_admin
        if payload.username is not None:
            user.username = username
        if payload.full_name is not None:
            profile = user.profile
            if profile:
                profile.full_name = payload.full_name
            else:
                db.add(UserProfile(user_id=user.id, full_name=payload.full_name))

    ensure_telegram_identity(db, user)
    db.commit()
    db.refresh(user)
    return issue_token_pair(db, user, response)


@router.post("/refresh", response_model=TokenPairResponse)
@limiter.limit("10/minute")
def refresh_tokens(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    raw_refresh_token = (
        payload.refresh_token
        if payload is not None and payload.refresh_token
        else request.cookies.get(settings.refresh_cookie_name, "")
    )
    if not raw_refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token отсутствует")
    try:
        token_payload = decode_token(raw_refresh_token, expected_type="refresh")
    except AuthError:
        raise _refresh_session_error(401, "Невалидный refresh token")

    jti = token_payload.get("jti")
    sub = token_payload.get("sub")
    if not isinstance(jti, str) or not sub:
        raise _refresh_session_error(401, "Невалидный refresh token")

    try:
        user_id = int(sub)
    except TypeError, ValueError:
        raise _refresh_session_error(401, "Невалидный refresh token")

    row = get_refresh_token_by_jti(db, jti)
    session_family_id = token_payload.get("sid")
    if session_family_id is None and row is not None and row.family_id == row.jti:
        # Migration 0033 backfills pre-family rows with family_id=jti. Accept
        # such a refresh token once so an existing browser can rotate into the
        # new sid-bearing format instead of being logged out during rollout.
        session_family_id = row.family_id
    if (
        row is None
        or row.user_id != user_id
        or not isinstance(session_family_id, str)
        or not session_family_id
        or row.family_id != session_family_id
    ):
        raise _refresh_session_error(401, "Refresh token не найден")

    if row.is_used:
        record_audit_event(
            db,
            action="session.refresh_replay",
            resource_type="session",
            target_user_id=row.user_id,
            resource_id=session_family_id,
        )
        revoke_refresh_token_family(db, row.user_id, session_family_id, commit=False)
        db.commit()
        raise _refresh_session_error(401, "Refresh token уже использован")

    if not is_refresh_token_valid(row, raw_refresh_token):
        raise _refresh_session_error(401, "Refresh token недействителен")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        revoke_refresh_token_family(db, row.user_id, session_family_id)
        raise _refresh_session_error(403, "Аккаунт заблокирован")

    if not consume_refresh_token(db, row, commit=False):
        db.rollback()
        record_audit_event(
            db,
            action="session.refresh_replay",
            resource_type="session",
            target_user_id=row.user_id,
            resource_id=session_family_id,
        )
        revoke_refresh_token_family(db, row.user_id, session_family_id, commit=False)
        db.commit()
        raise _refresh_session_error(401, "Refresh token уже использован")

    token_pair = issue_token_pair(
        db,
        user,
        response,
        commit=False,
        session_family_id=session_family_id,
    )
    db.commit()
    return token_pair


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    db: Session = Depends(get_db),
):
    raw_refresh_token = (
        payload.refresh_token
        if payload is not None and payload.refresh_token
        else request.cookies.get(settings.refresh_cookie_name, "")
    )
    _clear_refresh_cookie(response)
    revoked = False
    if raw_refresh_token:
        try:
            token_payload = decode_token(raw_refresh_token, expected_type="refresh")
        except AuthError:
            token_payload = {}
        jti = token_payload.get("jti")
        row = get_refresh_token_by_jti(db, jti) if isinstance(jti, str) else None
        session_family_id = token_payload.get("sid")
        if row and isinstance(session_family_id, str) and row.family_id == session_family_id:
            revoke_refresh_token_family(db, row.user_id, session_family_id)
            revoked = True

    if not revoked:
        access_token = extract_bearer_token(request.headers.get("Authorization"))
        try:
            access_payload = (
                decode_token(access_token, expected_type="access") if access_token else {}
            )
        except AuthError:
            access_payload = {}
            access_user_id = 0
        else:
            raw_access_user_id = access_payload.get("sub")
            try:
                access_user_id = (
                    int(raw_access_user_id) if isinstance(raw_access_user_id, str) else 0
                )
            except ValueError:
                access_user_id = 0
        access_family_id = access_payload.get("sid")
        if access_user_id > 0 and isinstance(access_family_id, str) and access_family_id:
            revoke_refresh_token_family(db, access_user_id, access_family_id)

    return {"status": "ok"}
