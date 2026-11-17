"""ORM models. Must stay in sync with supabase/migrations (checked by tests/test_schema_sync.py)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, Embedding, JSONType, Timestamps, UTCDateTime, UUIDPk, utcnow

EMBEDDING_DIMENSIONS = 768


def _user_fk() -> Any:
    return mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)


class Profile(Timestamps, Base):
    __tablename__ = "profiles"

    # Same value as auth.users.id in Supabase.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    locale: Mapped[str] = mapped_column(String(16), default="en")
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UserPreferences(UUIDPk, Timestamps, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    preferred_language: Mapped[str] = mapped_column(String(8), default="auto")  # auto | en | ta
    response_style: Mapped[str] = mapped_column(String(16), default="concise")  # concise | detailed
    llm_mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto | local | cloud
    voice_name: Mapped[str | None] = mapped_column(String(64))
    voice_speaking_rate: Mapped[float] = mapped_column(Float, default=1.0)
    wake_word_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    wake_word_sensitivity: Mapped[float] = mapped_column(Float, default=0.6)
    wake_word_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=4)
    # "Hold to talk" in Settings. Off by default: tapping the orb starts a hands-free conversation.
    push_to_talk_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    memory_auto_extract: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_retention_days: Mapped[int | None] = mapped_column(Integer)
    conversation_retention_days: Mapped[int | None] = mapped_column(Integer)
    store_voice_recordings: Mapped[bool] = mapped_column(Boolean, default=False)
    share_location: Mapped[bool] = mapped_column(Boolean, default=True)
    home_latitude: Mapped[float | None] = mapped_column(Float)
    home_longitude: Mapped[float | None] = mapped_column(Float)
    home_label: Mapped[str | None] = mapped_column(String(200))
    news_categories: Mapped[list[str]] = mapped_column(JSONType, default=lambda: ["world", "technology", "ai"])
    theme: Mapped[str] = mapped_column(String(8), default="system")


class Conversation(UUIDPk, Timestamps, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_last", "user_id", "last_message_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    channel: Mapped[str] = mapped_column(String(16), default="text")  # text | voice | automation
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Message(UUIDPk, Timestamps, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="complete")  # complete | error | cancelled
    channel: Mapped[str] = mapped_column(String(16), default="text")
    run_id: Mapped[str | None] = mapped_column(String(64))
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class Integration(UUIDPk, Timestamps, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(32))  # gmail | whatsapp | spotify
    status: Mapped[str] = mapped_column(String(16), default="disconnected")
    account_label: Mapped[str | None] = mapped_column(String(320))
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # non-secret settings only
    credentials_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credentials_wrapped_key: Mapped[bytes | None] = mapped_column(LargeBinary)
    credentials_key_id: Mapped[str | None] = mapped_column(String(200))
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = _user_fk()
    provider: Mapped[str] = mapped_column(String(32))
    code_verifier: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ToolPermission(UUIDPk, Timestamps, Base):
    __tablename__ = "tool_permissions"
    __table_args__ = (UniqueConstraint("user_id", "tool_name"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    tool_name: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)


class Memory(UUIDPk, Timestamps, Base):
    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32), default="fact")
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="user")  # user | assistant | conversation
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL")
    )
    importance: Mapped[int] = mapped_column(SmallInteger, default=3)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class VaultItem(UUIDPk, Timestamps, Base):
    __tablename__ = "vault_items"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))  # api_key | password | note | document | secret
    description: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(200))
    last_accessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AutomationRule(UUIDPk, Timestamps, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (Index("ix_automation_rules_due", "enabled", "next_run_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    schedule: Mapped[dict[str, Any]] = mapped_column(JSONType)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    pending_occurrence_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[str | None] = mapped_column(String(16))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    lock_token: Mapped[str | None] = mapped_column(String(64))


class TaskRun(UUIDPk, Timestamps, Base):
    __tablename__ = "task_runs"
    __table_args__ = (Index("ix_task_runs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    automation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("automation_rules.id", ondelete="SET NULL"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32))  # automation | approval | manual
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class Approval(UUIDPk, Timestamps, Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    task_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("task_runs.id", ondelete="SET NULL"))
    tool_name: Mapped[str] = mapped_column(String(64))
    tool_args: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class ExecutionLog(UUIDPk, Base):
    __tablename__ = "execution_logs"
    __table_args__ = (Index("ix_execution_logs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    run_id: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(32))  # llm_call | tool_call | automation
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(32))  # reminder | automation | approval | integration | system
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class VoiceSession(UUIDPk, Timestamps, Base):
    __tablename__ = "voice_sessions"

    user_id: Mapped[uuid.UUID] = _user_fk()
    room_name: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="created")  # created | active | ended | expired
    activation: Mapped[str] = mapped_column(String(16), default="push_to_talk")
    language: Mapped[str] = mapped_column(String(8), default="auto")
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_reason: Mapped[str | None] = mapped_column(String(64))
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class AuditLog(UUIDPk, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    actor: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


USER_OWNED_TABLES = [
    "user_preferences",
    "conversations",
    "messages",
    "integrations",
    "oauth_states",
    "tool_permissions",
    "memories",
    "vault_items",
    "automation_rules",
    "task_runs",
    "approvals",
    "execution_logs",
    "notifications",
    "voice_sessions",
    "audit_logs",
]
