from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitminiapp_api.schemas.nutrition_import import (
    ImportDiagnostic,
    ImportFoodRow,
    ImportSource,
    OriginalSummary,
    OriginalTotal,
)


class RowResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0, strict=True)
    food_id: int = Field(gt=0, strict=True)


class ImportResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    matches: list[RowResolution] = Field(max_length=2000)
    skipped_rows: list[Annotated[int, Field(ge=0, strict=True)]] = Field(max_length=2000)


class ImportConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)
    preview_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit confirmation is required")
        return value


class ImportCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)


class ImportPreviewRow(BaseModel):
    index: int
    status: Literal[
        "matched", "new", "ambiguous", "invalid", "skipped", "manual_resolution_required"
    ]
    source: ImportFoodRow
    action: dict[str, Any] | None
    issues: list[str]


class ImportPreview(BaseModel):
    id: str
    revision: int
    expires_at: datetime
    schema_version: Literal["nutrition-import-v1", "nutrition-import-v2"]
    parser_version: str
    content_sha256: str
    completeness: Literal["complete", "partial", "unknown"]
    source: ImportSource
    rows: list[ImportPreviewRow]
    original_totals: list[OriginalTotal]
    original_summaries: list[OriginalSummary]
    diagnostics: list[ImportDiagnostic]
    preview_signature: str


class ImportReceipt(BaseModel):
    entry_ids: list[int]
    preview_signature: str
