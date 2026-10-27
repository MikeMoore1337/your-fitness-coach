from __future__ import annotations

from fitminiapp_api.models.news import NewsDraftRevision

HERMES_SUBMISSION_MARKER = "hermes_narrow_intake"


def is_hermes_origin_draft(draft: NewsDraftRevision) -> bool:
    """Return whether a revision came through the canonical signed Hermes intake."""

    return draft.evidence_metadata.get("submitted_by") == HERMES_SUBMISSION_MARKER
