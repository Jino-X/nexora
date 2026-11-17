"""Builds provider chains: primary -> configured fallbacks -> offline router."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import Settings
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, LLMUnavailableError, TokenCallback
from app.llm.ollama import OllamaProvider
from app.llm.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("nexora.llm")


class FallbackLLM(LLMProvider):
    """Tries providers in order. A provider that is unreachable is skipped for a cooldown period so
    an offline Ollama does not add a connection timeout to every request."""

    name = "fallback"

    def __init__(self, providers: list[LLMProvider], cooldown_seconds: float = 30.0) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.cooldown = cooldown_seconds
        self._down_until: dict[str, float] = {}

    @property
    def model(self) -> str:  # type: ignore[override]
        return self.providers[0].model

    def _available(self) -> list[LLMProvider]:
        now = time.monotonic()
        live = [p for p in self.providers if self._down_until.get(p.name, 0) <= now]
        return live or self.providers[-1:]

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        last_error: Exception | None = None
        for provider in self._available():
            emitted = False

            async def _relay(tok: str, _cb: TokenCallback | None = on_token) -> None:
                nonlocal emitted
                emitted = True
                if _cb:
                    await _cb(tok)

            try:
                return await provider.chat(
                    messages, tools=tools, on_token=_relay, temperature=temperature, max_tokens=max_tokens
                )
            except LLMUnavailableError as exc:
                last_error = exc
                self._down_until[provider.name] = time.monotonic() + self.cooldown
                logger.warning("llm provider %s unavailable: %s", provider.name, exc)
                if emitted:
                    raise
        raise LLMUnavailableError(str(last_error) if last_error else "No LLM provider available")

    async def health(self) -> bool:
        return await self.providers[0].health()

    def primary_status(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            p.name: {"model": p.model, "offline": p.offline, "cooling_down": self._down_until.get(p.name, 0) > now}
            for p in self.providers
        }


def build_provider(name: str, settings: Settings, http: httpx.AsyncClient) -> LLMProvider | None:
    if name == "ollama":
        return OllamaProvider(
            http,
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            think=settings.ollama_think,
            keep_alive=settings.ollama_keep_alive,
            num_ctx=settings.ollama_num_ctx,
            timeout=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
        )
    if name == "openai_compatible":
        if not (settings.openai_compat_base_url and settings.openai_compat_api_key and settings.openai_compat_model):
            return None
        return OpenAICompatibleProvider(
            http,
            base_url=settings.openai_compat_base_url,
            api_key=settings.openai_compat_api_key.get_secret_value(),
            model=settings.openai_compat_model,
            timeout=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
        )
    if name == "offline":
        from app.assistant.offline import OfflineIntentRouter

        return OfflineIntentRouter()
    raise ValueError(f"unknown LLM provider '{name}'")


class LLMRouter:
    """Returns a provider chain that honours the user's `llm_mode` preference."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        names = [settings.llm_provider, *settings.llm_fallback_providers]
        if "offline" not in names:
            names.append("offline")
        self._providers: dict[str, LLMProvider] = {}
        for name in dict.fromkeys(names):
            provider = build_provider(name, settings, http)
            if provider is not None:
                self._providers[name] = provider
        self._chains: dict[str, FallbackLLM] = {}
        self._order = list(self._providers)

    def chain(self, mode: str = "auto") -> FallbackLLM:
        if mode not in self._chains:
            order = list(self._order)
            if mode == "local":
                order = [n for n in order if n in ("ollama", "offline")]
            elif mode == "cloud" and "openai_compatible" in order:
                order.remove("openai_compatible")
                order.insert(0, "openai_compatible")
            self._chains[mode] = FallbackLLM(
                [self._providers[n] for n in order], self.settings.llm_unhealthy_cooldown_seconds
            )
        return self._chains[mode]

    def provider(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._order)
