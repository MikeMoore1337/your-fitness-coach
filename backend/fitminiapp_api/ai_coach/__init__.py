"""Provider-neutral, generic-only AI Coach foundation."""

from fitminiapp_api.ai_coach.contracts import (
    AI_COACH_DATA_CLASS,
    AI_COACH_PERSONAL_PROMPT_VERSION,
    AI_COACH_PROMPT_VERSION,
    AI_COACH_SCHEMA_VERSION,
    AiCoachDataClass,
    AiCoachJob,
    AiCoachOutcome,
    AiCoachPersonalTool,
    AiCoachRequest,
    AiCoachResponse,
    ContextCitation,
    ContextRef,
    LlmPort,
    ProviderErrorCode,
    ProviderResult,
)

__all__ = [
    "AI_COACH_DATA_CLASS",
    "AI_COACH_PERSONAL_PROMPT_VERSION",
    "AI_COACH_PROMPT_VERSION",
    "AI_COACH_SCHEMA_VERSION",
    "AiCoachDataClass",
    "AiCoachJob",
    "AiCoachOutcome",
    "AiCoachPersonalTool",
    "AiCoachRequest",
    "AiCoachResponse",
    "ContextCitation",
    "ContextRef",
    "LlmPort",
    "ProviderErrorCode",
    "ProviderResult",
]
