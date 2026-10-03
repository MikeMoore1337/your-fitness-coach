from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AdminOperationReason = Literal[
    "security_incident",
    "abuse",
    "account_recovery",
    "support_request",
    "relationship_safety",
]


class AdminOperationRequest(BaseModel):
    reason: AdminOperationReason


class AdminUserStatusUpdate(AdminOperationRequest):
    is_active: bool


class AdminTrainerCapabilityUpdate(AdminOperationRequest):
    is_active: bool


class AdminUserSearchRow(BaseModel):
    id: int
    telegram_user_id: int | None = None
    username: str | None = None
    display_name: str
    is_active: bool
    is_trainer: bool
    is_root: bool
    created_at: datetime
    linked_providers: list[str] = Field(default_factory=list)


class AdminIdentityRow(BaseModel):
    provider: str
    identifier: str
    verified: bool
    last_login_at: datetime


class AdminRelationshipRow(BaseModel):
    id: int
    account_role: Literal["trainer", "client"]
    counterparty_user_id: int
    counterparty_name: str
    status: str
    created_at: datetime
    accepted_at: datetime | None = None
    ended_at: datetime | None = None
    ended_reason: str | None = None
    can_end: bool


class AdminJobRow(BaseModel):
    job_id: str
    kind: Literal["notification", "account_export"]
    user_id: int
    status: str
    created_at: datetime
    scheduled_for: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int | None = None
    error_code: str | None = None
    retry_allowed: bool


class AdminAuditRow(BaseModel):
    id: int
    action: str
    actor_user_id: int | None = None
    target_user_id: int | None = None
    resource_type: str
    resource_id: str | None = None
    reason: AdminOperationReason | None = None
    created_at: datetime


class AdminUserDetail(AdminUserSearchRow):
    identities: list[AdminIdentityRow] = Field(default_factory=list)
    relationships: list[AdminRelationshipRow] = Field(default_factory=list)
    jobs: list[AdminJobRow] = Field(default_factory=list)
    audit_history: list[AdminAuditRow] = Field(default_factory=list)


AdminLifecycleKpiKey = Literal[
    "activation_rate",
    "time_to_first_useful_action",
    "first_workout_completion_rate",
    "first_week_value_rate",
    "d1_meaningful_return",
    "d7_meaningful_return",
    "d30_meaningful_return",
    "missed_workout_recovery_conversion",
    "recovery_to_completion_rate",
    "time_to_recovery",
    "nutrition_repeat_rate",
    "progress_next_action_completion_rate",
    "weekly_loop_completion",
]


class AdminLifecycleKpi(BaseModel):
    key: AdminLifecycleKpiKey
    numerator: int
    denominator: int
    cohort_size: int
    rate_percent: float | None = None
    median_seconds: float | None = None
    window: str


class AdminLifecycleDataQuality(BaseModel):
    status: Literal["clean", "attention"]
    duplicate_milestones: int
    impossible_order: int
    client_success_without_server: int
    invalid_milestones: int
    excluded_role_accounts: int
    timezone_fallback_accounts: int


class AdminNutritionRepeatMetrics(BaseModel):
    eligible_opportunities: int
    confirmed_repeats: int
    repeat_rate_percent: float | None = None
    preview_count: int
    confirmed_preview_count: int
    preview_to_confirmed_percent: float | None = None
    median_seconds: float | None = None
    persistence_failures: int
    persistence_failure_rate_percent: float | None = None
    duplicate_prevention_count: int


class AdminFunnelResponse(BaseModel):
    period_days: int
    cohort_since: datetime
    cohort_until: datetime
    as_of: datetime
    cohort_size: int
    complete_weekly_cohorts: int
    eligible_real_account_count: int
    recovery_eligible_real_account_count: int
    nutrition_repeat_metrics: AdminNutritionRepeatMetrics
    analytics_provider_status: Literal["not_connected"]
    coverage_note: str
    effect_status: Literal["NOT_YET_PROVEN", "BASELINE_ONLY"]
    effect_note: str
    exclusions: list[str]
    data_quality: AdminLifecycleDataQuality
    kpis: list[AdminLifecycleKpi]
