"""Service container: one place that wires providers, so tests and workers can substitute them."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.assistant.runs import RunManager
from app.assistant.tools import ToolRegistry, build_registry
from app.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.security import TokenVerifier
from app.database.models import EMBEDDING_DIMENSIONS
from app.database.session import create_all, create_engine, create_sessionmaker
from app.integrations.credentials import CredentialStore
from app.integrations.gmail.client import GmailService
from app.integrations.gmail.oauth import GoogleOAuth
from app.integrations.maps.osm import OSMPlacesProvider
from app.integrations.music.providers import ITunesMusicProvider, MusicProvider, SpotifyMusicProvider
from app.integrations.news.rss import RSSNewsProvider
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.integrations.whatsapp.client import WhatsAppService
from app.integrations.youtube.client import YouTubeProvider
from app.llm.factory import LLMRouter
from app.memory.embeddings import HashingEmbeddings, OllamaEmbeddings, ResilientEmbeddings
from app.memory.service import MemoryService
from app.vault.encryption import EnvelopeCipher, build_cipher
from app.vault.service import VaultService
from app.voice.livekit_service import LiveKitService


@dataclass
class Services:
    settings: Settings
    http: httpx.AsyncClient
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    verifier: TokenVerifier
    rate_limiter: RateLimiter
    llm: LLMRouter
    embeddings: ResilientEmbeddings
    cipher: EnvelopeCipher | None
    memory: MemoryService
    vault: VaultService
    credentials: CredentialStore
    weather: OpenMeteoProvider
    places: OSMPlacesProvider
    news: RSSNewsProvider
    youtube: YouTubeProvider
    music: MusicProvider
    google_oauth: GoogleOAuth
    gmail: GmailService
    whatsapp: WhatsAppService
    livekit: LiveKitService
    tools: ToolRegistry
    runs: RunManager


async def build_services(
    settings: Settings, *, http: httpx.AsyncClient | None = None, engine: AsyncEngine | None = None
) -> Services:
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match the schema "
            f"({EMBEDDING_DIMENSIONS}); change both together (see docs/database.md)"
        )
    http = http or httpx.AsyncClient(
        timeout=settings.external_http_timeout_seconds,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        headers={"User-Agent": settings.osm_user_agent},
    )
    engine = engine or create_engine(settings)
    if settings.database_auto_create and settings.is_sqlite:
        await create_all(engine)
    cipher = build_cipher(settings)
    credentials = CredentialStore(cipher)

    if settings.embedding_provider == "ollama":
        primary = OllamaEmbeddings(
            http, settings.ollama_base_url, settings.ollama_embedding_model, settings.embedding_dimensions
        )
    else:
        primary = HashingEmbeddings(settings.embedding_dimensions)
    embeddings = ResilientEmbeddings(primary)

    music: MusicProvider
    if settings.spotify_client_id and settings.spotify_client_secret:
        music = SpotifyMusicProvider(
            http, settings.spotify_client_id, settings.spotify_client_secret.get_secret_value()
        )
    else:
        music = ITunesMusicProvider(http)

    google_oauth = GoogleOAuth(settings, http)
    return Services(
        settings=settings,
        http=http,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        verifier=TokenVerifier(settings),
        rate_limiter=RateLimiter(),
        llm=LLMRouter(settings, http),
        embeddings=embeddings,
        cipher=cipher,
        memory=MemoryService(embeddings, use_pgvector=not settings.is_sqlite),
        vault=VaultService(cipher, settings.vault_max_item_bytes),
        credentials=credentials,
        weather=OpenMeteoProvider(http, settings.open_meteo_url, settings.external_http_timeout_seconds),
        places=OSMPlacesProvider(
            http,
            nominatim_url=settings.nominatim_url,
            overpass_url=settings.overpass_url,
            user_agent=settings.osm_user_agent,
        ),
        news=RSSNewsProvider(http, settings.news_feeds),
        youtube=YouTubeProvider(
            http, settings.youtube_api_key.get_secret_value() if settings.youtube_api_key else None
        ),
        music=music,
        google_oauth=google_oauth,
        gmail=GmailService(google_oauth, credentials, http),
        whatsapp=WhatsAppService(credentials, http, settings.whatsapp_graph_api_version),
        livekit=LiveKitService(settings),
        tools=build_registry(),
        runs=RunManager(settings.run_buffer_ttl_seconds, settings.max_concurrent_runs_per_user),
    )


async def close_services(services: Services) -> None:
    await services.runs.shutdown()
    await services.http.aclose()
    await services.engine.dispose()
