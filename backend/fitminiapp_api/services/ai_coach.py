"""Compatibility facade for the AI Coach application service."""

from fitminiapp_api.ai_coach.service import (
    AiCoachService,
    ProviderCapability,
    ProviderCooldown,
    ai_coach_service,
)

__all__ = [
    "AiCoachService",
    "ProviderCapability",
    "ProviderCooldown",
    "ai_coach_service",
]
