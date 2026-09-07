"""Authenticated generic-only AI Coach endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from fitminiapp_api.ai_coach.contracts import AiCoachDataClass, AiCoachRequest, AiCoachResponse
from fitminiapp_api.ai_coach.service import ai_coach_service
from fitminiapp_api.api.dependencies.auth import require_user
from fitminiapp_api.core.rate_limit import limiter
from fitminiapp_api.db.session import get_db
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.ai_coach import AiCoachGenerateRequest

router = APIRouter()


@router.post("/generate", response_model=AiCoachResponse)
@limiter.limit("10/minute")
def generate_ai_coach_answer(
    request: Request,
    payload: AiCoachGenerateRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AiCoachResponse:
    # This route is physically generic-only: no profile, diary, workout,
    # trainer object or conversation history is loaded or passed downstream.
    internal_request = AiCoachRequest(
        job=payload.job,
        context_id=payload.context_id,
        message=payload.message,
        data_class=AiCoachDataClass.GENERIC,
    )
    return ai_coach_service.generate(
        db=db,
        request=internal_request,
        user_key=str(current_user.id),
        request_id=getattr(request.state, "request_id", None),
    )
