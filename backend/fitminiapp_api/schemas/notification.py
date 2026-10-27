from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReminderTemplateKey = Literal["meal_logging", "hydration", "movement_break"]
ReminderScheduleKind = Literal["times", "interval"]


class NotificationSettingUpdate(BaseModel):
    workout_reminders_enabled: bool | None = None
    weekly_check_in_reminders_enabled: bool | None = None
    measurement_reminders_enabled: bool | None = None
    meal_reminders_enabled: bool | None = None
    hydration_reminders_enabled: bool | None = None
    movement_reminders_enabled: bool | None = None
    telegram_enabled: bool | None = None
    reminder_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None


class NotificationSettingResponse(BaseModel):
    workout_reminders_enabled: bool
    weekly_check_in_reminders_enabled: bool
    measurement_reminders_enabled: bool
    meal_reminders_enabled: bool
    hydration_reminders_enabled: bool
    movement_reminders_enabled: bool
    telegram_enabled: bool
    telegram_linked: bool
    reminder_hour: int
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None


class ReminderTemplateUpdate(BaseModel):
    enabled: bool | None = None
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    times: list[time] | None = Field(default=None, max_length=3)
    window_start: time | None = None
    window_end: time | None = None
    interval_minutes: int | None = Field(default=None, ge=30, le=360)
    max_per_day: int | None = Field(default=None, ge=1, le=8)
    minimum_spacing_minutes: int | None = Field(default=None, ge=15, le=720)


class ReminderTemplateResponse(BaseModel):
    template_key: ReminderTemplateKey
    version: str
    label: str
    purpose: str
    schedule_kind: ReminderScheduleKind
    allowed_schedule: str
    quiet_hours_behavior: str
    deep_link: str
    suppression: str
    neutral_copy: str
    default_enabled: bool
    enabled: bool
    weekdays: list[int] = Field(min_length=1, max_length=7)
    times: list[time] = Field(max_length=3)
    window_start: time | None = None
    window_end: time | None = None
    interval_minutes: int | None = Field(default=None, ge=30, le=360)
    max_per_day: int = Field(ge=1, le=8)
    minimum_spacing_minutes: int = Field(ge=15, le=720)
    telegram_linked: bool
    telegram_enabled: bool
    channel_note: str


class NotificationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    body: str = Field(min_length=1, max_length=2000)
    scheduled_for: datetime


class NotificationResponse(BaseModel):
    id: int
    category: str
    event_kind: str
    title: str
    body: str
    created_at: datetime
    scheduled_for: datetime
    status: str
    delivery_status: str
    sent_at: datetime | None = None
    read_at: datetime | None = None
    action_url: str | None = None


class NotificationOpenResponse(BaseModel):
    destination: str
    stale: bool
    message: str | None = None


class NotificationReadAllResponse(BaseModel):
    updated: int


class WebPushSubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=1, max_length=128)
    auth: str = Field(min_length=1, max_length=64)


class WebPushSubscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2048)
    keys: WebPushSubscriptionKeys


class WebPushSubscriptionDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2048)


class WebPushConfigResponse(BaseModel):
    enabled: bool
    application_server_key: str | None = None


class WebPushStatusResponse(BaseModel):
    enabled: bool
    registered: bool


class WebPushSubscriptionResponse(BaseModel):
    status: Literal["registered"]
