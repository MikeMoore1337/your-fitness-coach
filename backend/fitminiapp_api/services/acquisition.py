from __future__ import annotations

from datetime import UTC

from sqlalchemy.orm import Session

from fitminiapp_api.models.acquisition import FirstTouchAttribution
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.acquisition import FirstTouchAttributionRequest


def save_first_touch_attribution(
    db: Session, user: User, payload: FirstTouchAttributionRequest
) -> bool:
    """Persist only the first valid attribution record for an account."""

    existing = db.get(FirstTouchAttribution, user.id)
    if existing is not None:
        return False
    db.add(
        FirstTouchAttribution(
            user_id=user.id,
            first_touch_source=payload.first_touch_source,
            first_touch_medium=payload.first_touch_medium,
            first_touch_campaign=payload.first_touch_campaign,
            first_landing_path=payload.first_landing_path,
            first_referrer=payload.first_referrer,
            first_touch_at=payload.first_touch_at.astimezone(UTC).replace(tzinfo=None),
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            utm_content=payload.utm_content,
            utm_term=payload.utm_term,
        )
    )
    db.flush()
    return True
