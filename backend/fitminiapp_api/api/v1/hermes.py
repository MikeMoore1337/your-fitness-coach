from __future__ import annotations

import hashlib
from typing import Literal, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import TypeAdapter, ValidationError

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.schemas.bot import HermesEditorialIntakeRequest, HermesEditorialIntakeResponse
from fitminiapp_api.services.news_hermes import (
    HermesIntakeError,
    accept_hermes_submission,
    verify_hermes_signature,
)

router = APIRouter()
_INTAKE_REQUEST_ADAPTER = TypeAdapter(HermesEditorialIntakeRequest)

_CLIENT_ERROR_CODES = {
    "source_not_allowlisted",
    "source_packet_invalid",
    "source_content_hash_mismatch",
    "source_packet_rejected",
    "source_publication_not_fresh",
    "source_item_missing",
    "cluster_missing",
    "draft_schema_invalid",
    "schema_version_unsupported",
    "skill_version_unsupported",
}
_CONFLICT_CODES = {
    "idempotency_conflict",
    "idempotency_nonce_conflict",
    "replay_detected",
    "replay_expired",
}


def _intake_http_error(error: HermesIntakeError) -> HTTPException:
    if error.code == "intake_disabled":
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="intake_disabled",
        )
    if error.code in {"key_not_found", "signature_headers_invalid", "signature_invalid"}:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if error.code == "signature_expired":
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signature_expired")
    if error.code == "rate_limited":
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")
    if error.code in _CONFLICT_CODES:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.code)
    if error.code in _CLIENT_ERROR_CODES:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.code)
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="intake_failed")


@router.post("/editorial/intake", response_model=HermesEditorialIntakeResponse)
async def receive_hermes_editorial_intake(
    request: Request,
    x_hermes_key_id: str | None = Header(default=None, alias="X-Hermes-Key-Id"),
    x_hermes_timestamp: str | None = Header(default=None, alias="X-Hermes-Timestamp"),
    x_hermes_nonce: str | None = Header(default=None, alias="X-Hermes-Nonce"),
    x_hermes_signature: str | None = Header(default=None, alias="X-Hermes-Signature"),
) -> HermesEditorialIntakeResponse:
    if not settings.hermes_intake_enabled:
        raise _intake_http_error(HermesIntakeError("intake_disabled"))
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
        raise _intake_http_error(exc) from exc
    try:
        payload = _INTAKE_REQUEST_ADAPTER.validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="payload_invalid") from exc
    try:
        with get_session_context() as db:
            result = accept_hermes_submission(
                db,
                payload,
                payload_hash=hashlib.sha256(body).hexdigest(),
            )
    except HermesIntakeError as exc:
        raise _intake_http_error(exc) from exc
    return HermesEditorialIntakeResponse(
        status=cast(Literal["accepted", "duplicate"], result.status),
        submission_id=result.submission_id,
        cluster_id=result.cluster_id,
        draft_id=result.draft_id,
        publication_policy=cast(
            Literal["blocked", "manual_required", "auto_eligible"],
            result.publication_policy,
        ),
        risk_reasons=list(result.risk_reasons),
        preview_text=result.preview_text,
    )
