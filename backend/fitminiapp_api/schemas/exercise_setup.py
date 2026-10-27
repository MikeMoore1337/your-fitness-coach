from __future__ import annotations

import unicodedata
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EXERCISE_SETUP_MEMORY_MAX_LENGTH = 240


def _normalize_setup_memory_body(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.strip()
    if not normalized:
        raise ValueError("Укажите короткую заметку о настройке упражнения")
    if any(ord(char) < 0x20 and char not in "\n\t" for char in normalized):
        raise ValueError("Заметка содержит недопустимые управляющие символы")
    return normalized


class ExerciseSetupMemorySaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(..., min_length=1, max_length=EXERCISE_SETUP_MEMORY_MAX_LENGTH)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        return _normalize_setup_memory_body(value)


class ExerciseSetupMemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    exercise_id: int
    body: str
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
