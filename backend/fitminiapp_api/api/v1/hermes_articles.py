from __future__ import annotations

import hashlib
from typing import Literal, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import TypeAdapter, ValidationError

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.schemas.articles import (
    HermesWebArticleIntakeRequest,
    HermesWebArticleIntakeResponse,
)
from fitminiapp_api.services.news_hermes import HermesIntakeError, verify_hermes_signature
from fitminiapp_api.services.web_articles import (
    HERMES_WEB_ARTICLE_SCHEMA_VERSION,
    WebArticleError,
    accept_hermes_article_submission,
)

router = APIRouter()
_REQUEST_ADAPTER = TypeAdapter(HermesWebArticleIntakeRequest)
_CONFLICT_CODES = {
    "idempotency_conflict",
    "idempotency_nonce_conflict",
    "replay_detected",
    "replay_expired",
    "slug_conflict",
}
_CLIENT_ERROR_CODES = {
    "candidate_missing",
    "candidate_not_ready",
    "hermes_candidate_not_allowed",
    "hermes_source_untrusted",
    "hermes_review_attestation_forbidden",
    "cta_contains_unallowed_fields",
    "cta_copy_invalid",
    "cta_destination_invalid",
    "nonce_mismatch",
    "schema_version_unsupported",
    "source_count_exceeded",
    "skill_version_unsupported",
    "slug_invalid",
}


def _http_error(error: HermesIntakeError | WebArticleError) -> HTTPException:
    if error.code == "intake_disabled":
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error.code)
    if error.code in {"key_not_found", "signature_headers_invalid", "signature_invalid"}:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if error.code == "signature_expired":
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error.code)
    if error.code == "rate_limited":
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=error.code)
    if error.code in _CONFLICT_CODES:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.code)
    if error.code in _CLIENT_ERROR_CODES:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.code)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="article_intake_failed"
    )


@router.post("/articles/intake", response_model=HermesWebArticleIntakeResponse)
async def receive_hermes_web_article_intake(
    request: Request,
    x_hermes_key_id: str | None = Header(default=None, alias="X-Hermes-Key-Id"),
    x_hermes_timestamp: str | None = Header(default=None, alias="X-Hermes-Timestamp"),
    x_hermes_nonce: str | None = Header(default=None, alias="X-Hermes-Nonce"),
    x_hermes_signature: str | None = Header(default=None, alias="X-Hermes-Signature"),
) -> HermesWebArticleIntakeResponse:
    if not settings.hermes_intake_enabled:
        raise _http_error(HermesIntakeError("intake_disabled"))
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.hermes_intake_max_body_bytes:
                raise HTTPException(status_code=413, detail="payload_too_large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="content_length_invalid") from exc
    body = await request.body()
    if len(body) > settings.hermes_intake_max_body_bytes:
        raise HTTPException(status_code=413, detail="payload_too_large")
    try:
        verify_hermes_signature(
            key_id=x_hermes_key_id or "",
            timestamp=x_hermes_timestamp or "",
            nonce=x_hermes_nonce or "",
            signature=x_hermes_signature or "",
            body=body,
        )
    except HermesIntakeError as exc:
        raise _http_error(exc) from exc
    try:
        payload = _REQUEST_ADAPTER.validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="payload_invalid") from exc
    if payload.request_nonce != (x_hermes_nonce or ""):
        raise _http_error(WebArticleError("nonce_mismatch"))
    if payload.schema_version != HERMES_WEB_ARTICLE_SCHEMA_VERSION:
        raise _http_error(WebArticleError("schema_version_unsupported"))
    try:
        with get_session_context() as db:
            result = accept_hermes_article_submission(
                db,
                payload,
                payload_hash=hashlib.sha256(body).hexdigest(),
            )
    except WebArticleError as exc:
        raise _http_error(exc) from exc
    return HermesWebArticleIntakeResponse(
        status=cast(Literal["accepted", "duplicate"], result.status),
        submission_id=result.submission_id,
        article_id=result.article_id,
        article_status=cast(
            Literal[
                "candidate",
                "researching",
                "draft",
                "review",
                "approved",
                "published",
                "update_required",
                "archived",
                "retracted",
            ],
            result.article_status,
        ),
        content_version=result.content_version,
        review_blockers=list(result.review_blockers),
    )
