from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from fitminiapp_api.nutrition_label.contracts import StrictModel
from fitminiapp_api.nutrition_label.vision import (
    VISION_MAX_RESPONSE_BYTES,
    GroqVisionTransport,
    VisionFallbackAdapter,
    VisionProposalError,
    _reject_non_finite,
    _unique_object,
    build_groq_vision_transport,
)

MEAL_VISION_POLICY_REVISION = "nutrition-photo-meal-v1"
MEAL_VISION_PROMPT_VERSION = "nutrition-photo-meal-groq-qwen38-v1"
MEAL_VISION_MAX_CANDIDATES = 8
_MEAL_VISION_SCHEMA_NAME = "nutrition_photo_meal_extraction_v1"
_MEAL_VISION_INSTRUCTION = """Identify only foods visibly present in this meal photo.
Return approximate nutrition for each visible food and its suggested portion. Use null when
identity, portion, or nutrition is not readable or is uncertain. Portion and nutrition are
estimates for review, never exact measurements. Do not identify people, body composition, body
measurements, medical conditions, health status, or anything outside the visible food. Do not use
user history or infer ingredients that are not visually supported. If the image is unsupported or
no food can be identified, return an empty candidates list with an appropriate warning."""

Confidence = Literal["high", "medium", "low", "unknown"]
MealWarning = Literal[
    "identity_uncertain",
    "portion_uncertain",
    "nutrition_uncertain",
    "unsupported_image",
]


class MealVisionCandidateExtraction(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    portion_amount: float | None = Field(default=None, gt=0, le=5000, allow_inf_nan=False)
    portion_unit: Literal["g", "ml", "serving"] | None = None
    portion_confidence: Confidence = "unknown"
    identity_confidence: Confidence = "unknown"
    nutrition_confidence: Confidence = "unknown"
    energy_kcal: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    protein_g: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    fat_g: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    carbs_g: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate name must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_portion(self) -> MealVisionCandidateExtraction:
        if (self.portion_amount is None) != (self.portion_unit is None):
            raise ValueError("portion amount and unit must be provided together")
        return self


class MealVisionExtraction(StrictModel):
    candidates: list[MealVisionCandidateExtraction] = Field(
        default_factory=list,
        max_length=MEAL_VISION_MAX_CANDIDATES,
    )
    warnings: list[MealWarning] = Field(default_factory=list, max_length=8)


class GroqMealVisionAdapter:
    provider_class = "groq"
    prompt_version = MEAL_VISION_PROMPT_VERSION

    def __init__(self, transport: GroqVisionTransport) -> None:
        self._transport = transport
        self.model_class = transport.model_class

    def recognize(
        self,
        normalized_png: bytes,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> bytes:
        return self._transport.complete(
            normalized_png,
            instruction=_MEAL_VISION_INSTRUCTION,
            schema_name=_MEAL_VISION_SCHEMA_NAME,
            schema=MealVisionExtraction.model_json_schema(),
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )


def build_meal_vision_adapter() -> VisionFallbackAdapter | None:
    transport = build_groq_vision_transport()
    return GroqMealVisionAdapter(transport) if transport is not None else None


def validate_meal_vision_proposal(
    response: bytes,
    *,
    provider_class: str,
    model_class: str,
    prompt_version: str,
) -> MealVisionExtraction:
    del provider_class, model_class, prompt_version
    if not isinstance(response, bytes) or not response or len(response) > VISION_MAX_RESPONSE_BYTES:
        raise VisionProposalError("response_size")
    try:
        return MealVisionExtraction.model_validate(
            json.loads(
                response.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_non_finite,
            )
        )
    except VisionProposalError:
        raise
    except (UnicodeDecodeError, ValidationError, ValueError, TypeError, RecursionError) as exc:
        raise VisionProposalError("invalid_provider_response") from exc


__all__ = [
    "MEAL_VISION_MAX_CANDIDATES",
    "MEAL_VISION_POLICY_REVISION",
    "MEAL_VISION_PROMPT_VERSION",
    "Confidence",
    "GroqMealVisionAdapter",
    "MealVisionCandidateExtraction",
    "MealVisionExtraction",
    "build_meal_vision_adapter",
    "validate_meal_vision_proposal",
]
