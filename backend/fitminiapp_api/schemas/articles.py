from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from fitminiapp_api.schemas.bot import HermesGenerationProvenance

ArticleKind = Literal[
    "evergreen_explainer",
    "practical_guide",
    "evidence_review",
    "myth_busting",
    "research_update",
    "comparison",
    "product_education",
]
SearchIntent = Literal["informational", "how_to", "comparison", "definition", "evidence", "mixed"]
ArticleStatus = Literal[
    "candidate",
    "researching",
    "draft",
    "review",
    "approved",
    "published",
    "update_required",
    "archived",
    "retracted",
]
ArticleRiskLevel = Literal["low", "moderate", "high", "critical", "unknown"]
ArticleEvidenceLevel = Literal[
    "high", "moderate", "limited", "preliminary", "conflicting", "unknown"
]


class ArticleBodySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(..., min_length=1, max_length=180)
    paragraphs: list[str] = Field(..., min_length=1, max_length=8)
    points: list[str] = Field(default_factory=list, max_length=12)


class ArticleClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    claim_text: str = Field(..., min_length=1, max_length=800)
    normalized_claim: str = Field(..., min_length=1, max_length=800)


class ArticleSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    title: str = Field(..., min_length=1, max_length=240)
    publisher: str = Field(..., min_length=1, max_length=160)
    url: HttpUrl
    source_type: str = Field(..., min_length=1, max_length=48)
    published_at: str | None = Field(default=None, max_length=32)
    limitations: str = Field(default="", max_length=800)

    @model_validator(mode="after")
    def require_https(self) -> ArticleSource:
        if self.url.scheme != "https":
            raise ValueError("article sources must use HTTPS")
        return self


class ArticleClaimSourceMatrixItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    source_ids: list[str] = Field(..., min_length=1, max_length=15)
    support_level: Literal["supports", "partially_supports", "does_not_support", "unclear"]
    limitations: str = Field(default="", max_length=1000)
    review_status: Literal["pending", "verified", "blocked"] = "pending"


class ArticlePerson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=160)
    type: Literal["Organization", "Person"]


class HermesWebArticleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., min_length=3, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(..., min_length=1, max_length=180)
    description: str = Field(..., min_length=1, max_length=320)
    lead: str = Field(..., min_length=1, max_length=1200)
    body_sections: list[ArticleBodySection] = Field(..., min_length=2, max_length=24)
    topics: list[str] = Field(..., min_length=1, max_length=12)
    article_kind: ArticleKind
    search_intent: SearchIntent
    primary_query: str = Field(..., min_length=1, max_length=240)
    secondary_queries: list[str] = Field(default_factory=list, max_length=20)
    risk_level: ArticleRiskLevel
    evidence_level: ArticleEvidenceLevel
    claims: list[ArticleClaim] = Field(..., min_length=1, max_length=80)
    sources: list[ArticleSource] = Field(..., min_length=1, max_length=30)
    claim_source_matrix: list[ArticleClaimSourceMatrixItem] = Field(
        ..., min_length=1, max_length=80
    )
    author: ArticlePerson
    editor: ArticlePerson
    domain_reviewer: ArticlePerson | None = None
    related_slugs: list[str] = Field(default_factory=list, max_length=8)
    cta: dict[str, str] = Field(default_factory=dict)
    evergreen_score: int = Field(..., ge=0, le=100)
    product_relevance: int = Field(..., ge=0, le=100)
    editorial_value: int = Field(..., ge=0, le=100)
    web_article_potential_reasons: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_matrix(self) -> HermesWebArticleProposal:
        claim_ids = {claim.claim_id for claim in self.claims}
        source_ids = {source.source_id for source in self.sources}
        matrix_claim_ids = {item.claim_id for item in self.claim_source_matrix}
        if matrix_claim_ids != claim_ids:
            raise ValueError("claim_source_matrix must cover each claim exactly once")
        if any(
            source_id not in source_ids
            for item in self.claim_source_matrix
            for source_id in item.source_ids
        ):
            raise ValueError("claim_source_matrix references an unknown source")
        if self.risk_level in {"high", "critical"} and self.domain_reviewer is None:
            raise ValueError("domain_reviewer is required for high-risk articles")
        if len(self.sources) < 2 and self.article_kind == "evidence_review":
            raise ValueError("evidence_review requires multiple sources")
        return self


class HermesWebArticleIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["hermes-web-article-intake-v1"] = "hermes-web-article-intake-v1"
    idempotency_key: str = Field(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    request_nonce: str = Field(..., min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    candidate_id: str = Field(..., min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    research_version: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.:-]+$")
    article: HermesWebArticleProposal
    provenance: HermesGenerationProvenance


class OwnerWebArticlePublishRequest(BaseModel):
    """Explicit root-owner editorial release; does not attest scientific verification."""

    model_config = ConfigDict(extra="forbid")

    article: HermesWebArticleProposal
    acknowledge_unverified_evidence: Literal[True]
    generated_with_ai: bool = True


class OwnerWebArticlePublishResponse(BaseModel):
    article_id: str
    slug: str
    article_status: Literal["published"]
    content_version: int
    canonical_url: str
    editorial_decision: Literal["root_owner_publication"]
    scientific_verification: Literal["not_attested"]



class OwnerArticleReviewRow(BaseModel):
    """Authenticated Root-only read model; cannot authorize publication."""

    article_id: str
    slug: str
    title: str
    article_status: Literal["draft", "review", "update_required"]
    content_version: int
    content_hash: str
    candidate_id: str | None
    risk_level: ArticleRiskLevel
    evidence_level: ArticleEvidenceLevel
    source_count: int
    claim_count: int
    pending_claim_count: int
    review_blockers: list[str]
    generated_with_ai: bool
    research_version: str
    updated_at: datetime | None


class OwnerArticleReviewDetail(OwnerArticleReviewRow):
    """Exact content and provenance for a human Root decision, never a GO."""

    description: str
    lead: str
    body_sections: list[ArticleBodySection]
    topics: list[str]
    claims: list[ArticleClaim]
    sources: list[ArticleSource]
    claim_source_matrix: list[ArticleClaimSourceMatrixItem]
    domain_reviewer: ArticlePerson | None
    provider: str
    model: str
    prompt_version: str
    skill_version: str


class WebArticleCard(BaseModel):
    slug: str
    title: str
    description: str
    lead: str
    topics: list[str]
    article_kind: ArticleKind
    published_at: datetime
    updated_at: datetime
    canonical_url: str


class WebArticleResponse(WebArticleCard):
    body_sections: list[ArticleBodySection]
    search_intent: SearchIntent
    primary_query: str
    secondary_queries: list[str]
    risk_level: ArticleRiskLevel
    evidence_level: ArticleEvidenceLevel
    claims: list[ArticleClaim]
    sources: list[ArticleSource]
    claim_source_matrix: list[ArticleClaimSourceMatrixItem]
    author: ArticlePerson
    editor: ArticlePerson
    domain_reviewer: ArticlePerson | None
    related_slugs: list[str]
    cta: dict[str, str]
    content_version: int
    generated_with_ai: bool
    research_assistance: bool


class HermesWebArticleIntakeResponse(BaseModel):
    status: Literal["accepted", "duplicate"]
    submission_id: str
    article_id: str
    article_status: ArticleStatus
    content_version: int
    review_blockers: list[str]
