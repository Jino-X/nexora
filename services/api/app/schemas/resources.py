"""Request/response models for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

# ---- profile & preferences ---------------------------------------------------------------------


class ProfileOut(ORMModel):
    id: uuid.UUID
    email: str | None
    display_name: str | None
    avatar_url: str | None
    timezone: str
    locale: str
    onboarded_at: datetime | None
    created_at: datetime


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=120)
    avatar_url: str | None = Field(None, max_length=1024)
    timezone: str | None = Field(None, max_length=64)
    locale: str | None = Field(None, max_length=16)


class PreferencesOut(ORMModel):
    preferred_language: str
    response_style: str
    llm_mode: str
    voice_name: str | None
    voice_speaking_rate: float
    wake_word_enabled: bool
    wake_word_sensitivity: float
    wake_word_cooldown_seconds: int
    push_to_talk_enabled: bool
    memory_enabled: bool
    memory_auto_extract: bool
    memory_retention_days: int | None
    conversation_retention_days: int | None
    store_voice_recordings: bool
    share_location: bool
    home_latitude: float | None
    home_longitude: float | None
    home_label: str | None
    news_categories: list[str]
    theme: str


class PreferencesUpdate(BaseModel):
    preferred_language: Literal["auto", "en", "ta"] | None = None
    response_style: Literal["concise", "detailed"] | None = None
    llm_mode: Literal["auto", "local", "cloud"] | None = None
    voice_name: str | None = Field(None, max_length=64)
    voice_speaking_rate: float | None = Field(None, ge=0.5, le=2.0)
    wake_word_enabled: bool | None = None
    wake_word_sensitivity: float | None = Field(None, ge=0.0, le=1.0)
    wake_word_cooldown_seconds: int | None = Field(None, ge=1, le=60)
    push_to_talk_enabled: bool | None = None
    memory_enabled: bool | None = None
    memory_auto_extract: bool | None = None
    memory_retention_days: int | None = Field(None, ge=1, le=3650)
    conversation_retention_days: int | None = Field(None, ge=1, le=3650)
    store_voice_recordings: bool | None = None
    share_location: bool | None = None
    home_latitude: float | None = Field(None, ge=-90, le=90)
    home_longitude: float | None = Field(None, ge=-180, le=180)
    home_label: str | None = Field(None, max_length=200)
    news_categories: list[str] | None = Field(None, max_length=8)
    theme: Literal["system", "light", "dark"] | None = None
    clear_fields: list[
        Literal[
            "memory_retention_days",
            "conversation_retention_days",
            "home_latitude",
            "home_longitude",
            "home_label",
            "voice_name",
        ]
    ] = Field(default_factory=list)


class OnboardingIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    timezone: str = Field(max_length=64)
    preferred_language: Literal["auto", "en", "ta"] = "auto"
    news_categories: list[str] = Field(default_factory=lambda: ["world", "technology", "ai"], max_length=8)
    memory_enabled: bool = True
    home_label: str | None = Field(None, max_length=200)
    home_latitude: float | None = Field(None, ge=-90, le=90)
    home_longitude: float | None = Field(None, ge=-180, le=180)


class MeOut(BaseModel):
    profile: ProfileOut
    preferences: PreferencesOut


# ---- conversations -----------------------------------------------------------------------------


class ConversationOut(ORMModel):
    id: uuid.UUID
    title: str
    channel: str
    archived: bool
    last_message_at: datetime
    created_at: datetime


class MessageOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str
    channel: str
    run_id: str | None
    tool_calls: list[dict[str, Any]]
    meta: dict[str, Any]
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    title: str = Field("New conversation", max_length=200)


class ConversationUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    archived: bool | None = None


# ---- assistant ---------------------------------------------------------------------------------


class LocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    label: str | None = Field(None, max_length=200)


class RunCreate(BaseModel):
    message: str = Field("", max_length=8000)
    conversation_id: uuid.UUID | None = None
    location: LocationIn | None = None
    language: Literal["auto", "en", "ta"] | None = None
    regenerate: bool = False


class RunOut(BaseModel):
    run_id: str
    conversation_id: uuid.UUID
    status: str
    events_url: str


class RunStatus(BaseModel):
    run_id: str
    conversation_id: uuid.UUID
    status: str
    event_count: int
    text: str


# ---- memories ----------------------------------------------------------------------------------

MemoryKind = Literal["profile", "preference", "fact", "project", "conversation_summary", "note"]


class MemoryOut(ORMModel):
    id: uuid.UUID
    kind: str
    content: str
    source: str
    importance: int
    pinned: bool
    embedding_model: str | None
    source_conversation_id: uuid.UUID | None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    score: float | None = None


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: MemoryKind = "fact"
    importance: int = Field(3, ge=1, le=5)
    pinned: bool = False


class MemoryUpdate(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=4000)
    kind: MemoryKind | None = None
    importance: int | None = Field(None, ge=1, le=5)
    pinned: bool | None = None
    expires_at: datetime | None = None


# ---- vault -------------------------------------------------------------------------------------

VaultKind = Literal["api_key", "password", "note", "document", "secret"]


class VaultItemOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: str
    description: str | None
    content_type: str | None
    size_bytes: int
    key_id: str
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("key_id")
    @classmethod
    def _key_label(cls, value: str) -> str:
        return value.split(":", 1)[0] + ":" + value.rsplit(":", 1)[-1][-8:]


class VaultItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: VaultKind
    description: str | None = Field(None, max_length=500)
    secret: str | None = Field(None, max_length=100_000)
    fields: dict[str, str] | None = None
    file_base64: str | None = None
    content_type: str | None = Field(None, max_length=120)


class VaultItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    secret: str | None = Field(None, max_length=100_000)
    fields: dict[str, str] | None = None
    file_base64: str | None = None


class VaultReveal(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    secret: str | None = None
    fields: dict[str, str] | None = None
    file_base64: str | None = None
    content_type: str | None = None


class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    details: dict[str, Any]
    created_at: datetime


# ---- automations, tasks, approvals, notifications --------------------------------------------------


class AutomationOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: str
    config: dict[str, Any]
    schedule: dict[str, Any]
    timezone: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    consecutive_failures: int
    max_retries: int
    created_at: datetime
    schedule_description: str | None = None


class AutomationCreate(BaseModel):
    name: str = Field("", max_length=120)
    kind: Literal["morning_briefing", "news_summary", "email_summary", "reminder", "assistant_prompt"]
    schedule: dict[str, Any]
    timezone: str | None = Field(None, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AutomationUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    schedule: dict[str, Any] | None = None
    timezone: str | None = Field(None, max_length=64)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class SchedulePreviewIn(BaseModel):
    schedule: dict[str, Any]
    timezone: str = Field(max_length=64)


class SchedulePreviewOut(BaseModel):
    description: str
    next_runs: list[datetime]


class TaskRunOut(ORMModel):
    id: uuid.UUID
    automation_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    kind: str
    title: str
    status: str
    scheduled_for: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    attempt: int
    result: dict[str, Any]
    error: str | None
    created_at: datetime


class ApprovalOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    tool_name: str
    tool_args: dict[str, Any]
    summary: str
    status: str
    expires_at: datetime
    decided_at: datetime | None
    result: dict[str, Any]
    created_at: datetime


class NotificationOut(ORMModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class MarkReadIn(BaseModel):
    ids: list[uuid.UUID] | None = Field(None, max_length=200)


# ---- integrations & permissions -----------------------------------------------------------------


class IntegrationStatus(BaseModel):
    provider: str
    name: str
    description: str
    kind: Literal["per_user", "server"]
    available: bool  # server configured for this integration
    status: str  # connected | disconnected | error | not_configured | ready
    account_label: str | None = None
    scopes: list[str] = []
    connected_at: datetime | None = None
    last_error: str | None = None
    setup_hint: str | None = None
    tools: list[str] = []


class WhatsAppConfigIn(BaseModel):
    phone_number_id: str = Field(pattern=r"^\d{6,30}$")
    access_token: str = Field(min_length=20, max_length=1000)
    business_account_id: str | None = Field(None, pattern=r"^\d{6,30}$")
    display_phone_number: str | None = Field(None, max_length=32)


class ToolPermissionOut(BaseModel):
    tool_name: str
    category: str
    description: str
    risk: str
    approval_policy: str
    integration: str | None
    enabled: bool
    requires_approval: bool


class ToolPermissionUpdate(BaseModel):
    enabled: bool | None = None
    requires_approval: bool | None = None


# ---- voice -------------------------------------------------------------------------------------


class VoiceSessionCreate(BaseModel):
    activation: Literal["push_to_talk", "wake_word"] = "push_to_talk"
    conversation_id: uuid.UUID | None = None
    language: Literal["auto", "en", "ta"] | None = None
    hold_to_talk: bool = False  # manual turns (start_turn/end_turn RPCs) instead of automatic turn detection


class VoiceSessionOut(BaseModel):
    session_id: uuid.UUID
    room_name: str
    server_url: str
    participant_token: str
    participant_identity: str
    conversation_id: uuid.UUID
    expires_at: datetime


class VoiceSessionSummary(ORMModel):
    id: uuid.UUID
    room_name: str
    status: str
    activation: str
    language: str
    conversation_id: uuid.UUID | None
    started_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None
    turn_count: int
    created_at: datetime


class VoiceTurnIn(BaseModel):
    session_id: uuid.UUID
    room_name: str = Field(max_length=128)
    participant_identity: str = Field(max_length=128)
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(None, max_length=8)


class VoiceSessionEventIn(BaseModel):
    session_id: uuid.UUID
    room_name: str = Field(max_length=128)
    event: Literal["agent_joined", "session_started", "session_ended", "metrics"]
    reason: str | None = Field(None, max_length=64)
    metrics: dict[str, float] | None = None
