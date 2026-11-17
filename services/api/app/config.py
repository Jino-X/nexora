"""Application settings loaded from the environment (see .env.example)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_NEWS_FEEDS: list[dict[str, str]] = [
    {"name": "BBC News - World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "category": "world"},
    {
        "name": "The Hindu - National",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "category": "india",
    },
    {"name": "BBC News - Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "category": "business"},
    {
        "name": "BBC News - Science",
        "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "category": "science",
    },
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "technology"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "technology"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "ai"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "category": "ai"},
    {
        "name": "MIT Technology Review - AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "category": "ai",
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- application -------------------------------------------------------------------------
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Nexora"
    api_public_url: str = "http://localhost:8000"
    web_app_url: str = "http://localhost:3000"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"
    log_json: bool = True
    max_request_bytes: int = 6_000_000

    # ---- database ----------------------------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./nexora.db"
    database_echo: bool = False
    # Set to 0 when connecting through a transaction-mode pooler (Supavisor port 6543).
    database_statement_cache_size: int = 100
    database_auto_create: bool = True  # create tables on startup (SQLite/dev only)

    # ---- authentication ------------------------------------------------------------------------
    supabase_url: str | None = None
    supabase_jwt_secret: SecretStr | None = None  # legacy HS256 secret (optional with JWKS)
    supabase_service_role_key: SecretStr | None = None  # server-only; used for account deletion
    supabase_jwt_audience: str = "authenticated"
    auth_dev_mode: bool = False
    dev_jwt_secret: SecretStr | None = None
    dev_token_ttl_seconds: int = 60 * 60 * 12

    # Service-to-service key used by the voice agent (never sent to browsers).
    internal_service_key: SecretStr | None = None

    # ---- LLM ---------------------------------------------------------------------------------
    llm_provider: Literal["ollama", "openai_compatible", "offline"] = "ollama"
    llm_fallback_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["offline"])
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_think: bool = False
    ollama_keep_alive: str = "30m"
    ollama_num_ctx: int = 8192
    openai_compat_base_url: str | None = None
    openai_compat_api_key: SecretStr | None = None
    openai_compat_model: str | None = None
    llm_timeout_seconds: float = 90.0
    llm_temperature: float = 0.4
    llm_max_context_messages: int = 16
    llm_max_tool_steps: int = 4
    llm_unhealthy_cooldown_seconds: float = 30.0

    embedding_provider: Literal["ollama", "hashing"] = "ollama"
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # ---- vault / key management ----------------------------------------------------------------
    key_provider: Literal["local", "aws_kms"] = "local"
    # Comma separated "<key-id>:<base64 32 bytes>" entries. Keep old keys for decryption.
    vault_master_keys: SecretStr | None = None
    vault_active_key_id: str | None = None
    aws_kms_key_id: str | None = None
    aws_region: str | None = None
    vault_max_item_bytes: int = 2_000_000
    # Require a sign-in within N minutes (Supabase `amr` claim) before revealing secrets. 0 disables.
    vault_reauth_max_age_minutes: int = 0

    # ---- LiveKit -----------------------------------------------------------------------------
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: SecretStr | None = None
    livekit_agent_name: str = "nexora-voice"
    voice_token_ttl_seconds: int = 600
    voice_max_session_seconds: int = 900

    # ---- integrations --------------------------------------------------------------------------
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: str | None = None  # defaults to {api_public_url}/api/v1/integrations/gmail/callback

    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_webhook_verify_token: SecretStr | None = None
    whatsapp_app_secret: SecretStr | None = None

    youtube_api_key: SecretStr | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: SecretStr | None = None

    nominatim_url: str = "https://nominatim.openstreetmap.org"
    # Comma-separated, tried in order. The main public server is often at capacity (slow or 502): a mirror goes first.
    overpass_url: str = (
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter,https://overpass-api.de/api/interpreter"
    )
    osm_user_agent: str = "Nexora/0.1 (self-hosted personal assistant)"
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"
    news_feeds: Annotated[list[dict[str, str]], NoDecode] = Field(default_factory=lambda: list(DEFAULT_NEWS_FEEDS))
    external_http_timeout_seconds: float = 12.0

    # ---- automations ---------------------------------------------------------------------------
    run_scheduler_in_api: bool = True
    scheduler_poll_seconds: float = 15.0
    scheduler_batch_size: int = 20
    automation_timeout_seconds: float = 120.0

    # ---- limits --------------------------------------------------------------------------------
    rate_limit_per_minute: int = 120
    assistant_rate_limit_per_minute: int = 20
    voice_rate_limit_per_minute: int = 10
    max_concurrent_runs_per_user: int = 3
    run_buffer_ttl_seconds: int = 600

    # ------------------------------------------------------------------------------------------
    @field_validator("cors_origins", "llm_fallback_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("news_feeds", mode="before")
    @classmethod
    def _parse_feeds(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            return json.loads(value)
        if isinstance(value, str):
            return list(DEFAULT_NEWS_FEEDS)
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.app_env == "production":
            problems = []
            if self.auth_dev_mode:
                problems.append("AUTH_DEV_MODE must be false in production")
            if not self.database_url.startswith("postgresql"):
                problems.append("DATABASE_URL must point to PostgreSQL in production")
            if not (self.supabase_url or self.supabase_jwt_secret):
                problems.append("SUPABASE_URL (JWKS) or SUPABASE_JWT_SECRET is required")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not contain '*'")
            if self.key_provider == "local" and not self.vault_master_keys:
                problems.append("VAULT_MASTER_KEYS (or KEY_PROVIDER=aws_kms) is required")
            if problems:
                raise ValueError("Invalid production configuration: " + "; ".join(problems))
        if self.auth_dev_mode and not self.dev_jwt_secret:
            raise ValueError("AUTH_DEV_MODE=true requires DEV_JWT_SECRET (run infrastructure/scripts/bootstrap-env.py)")
        return self

    # ---- derived -------------------------------------------------------------------------------
    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def livekit_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def gmail_redirect_uri(self) -> str:
        return self.google_redirect_uri or f"{self.api_public_url}/api/v1/integrations/gmail/callback"

    @property
    def vault_configured(self) -> bool:
        if self.key_provider == "aws_kms":
            return bool(self.aws_kms_key_id)
        return bool(self.vault_master_keys)


@lru_cache
def get_settings() -> Settings:
    return Settings()
