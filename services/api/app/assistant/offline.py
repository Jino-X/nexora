"""Deterministic offline intent router.

Used when no LLM is reachable (Ollama stopped, no cloud fallback configured). It maps clear requests
to the same registered tools and replies with each tool's own summary. Responses carry
`offline=True` and the UI labels them "Offline mode", so they are never presented as AI answers."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.llm.base import ChatMessage, LLMProvider, LLMResponse, TokenCallback, ToolCall

CONTEXT_RE = re.compile(r"\[context\] now=(\S+) tz=(\S+)")

PLACE_WORDS = {
    "petrol_pump": r"petrol|fuel|diesel|gas station|bunk|பெட்ரோல்",
    "ev_charging": r"ev charg|charging station",
    "hotel": r"hotels?|lodges?|stay|accommodation|ஹோட்டல்",
    "restaurant": r"restaurants?|food|eat|dinner|lunch|biryani|உணவகம்",
    "cafe": r"cafes?|coffee|tea shop",
    "hospital": r"hospitals?|clinics?|doctor|மருத்துவமனை",
    "pharmacy": r"pharmac(y|ies)|medical shop|chemist|medicine",
    "atm": r"\batms?\b|cash",
    "supermarket": r"supermarket|grocery",
    "parking": r"parking",
    "police": r"police",
}

HELP = (
    "I'm in offline mode right now (no language model is connected), so I can only handle clear requests: "
    "weather, news, nearby places, YouTube, music, reminders, saving or recalling memories, emails and your "
    'daily briefing. For example: "weather in Chennai", "nearest petrol pump", "remind me to call Ravi '
    'tomorrow at 10am". Start Ollama (`ollama serve` + `ollama pull qwen3:8b`) for full conversations.'
)


def _now(messages: list[ChatMessage]) -> tuple[datetime, str]:
    for msg in messages:
        if msg.role == "system" and (match := CONTEXT_RE.search(msg.content)):
            try:
                tz = match.group(2)
                return datetime.fromisoformat(match.group(1)).astimezone(ZoneInfo(tz)), tz
            except (ValueError, KeyError):
                break
    return datetime.now(ZoneInfo("UTC")), "UTC"


def parse_when(text: str, now: datetime) -> datetime | None:
    """Small relative-time parser for reminders: 'in 10 minutes', 'tomorrow at 9am', 'at 17:30'."""
    t = text.lower()
    if m := re.search(r"in (\d{1,3}) (minute|min|hour|hr)s?", t):
        delta = timedelta(minutes=int(m.group(1))) if m.group(2).startswith("m") else timedelta(hours=int(m.group(1)))
        return (now + delta).replace(second=0, microsecond=0)
    day = now.date()
    if "day after tomorrow" in t:
        day = day + timedelta(days=2)
    elif "tomorrow" in t or "நாளை" in t:
        day = day + timedelta(days=1)
    hour, minute = 9, 0
    if m := re.search(r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t):
        hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3) == "pm":
            hour += 12
    elif m := re.search(r"\bat\s*(\d{1,2}):(\d{2})\b", t):
        hour, minute = int(m.group(1)), int(m.group(2))
    elif "evening" in t:
        hour = 18
    elif "afternoon" in t:
        hour = 14
    elif "tonight" in t or "night" in t:
        hour = 21
    elif not any(w in t for w in ("tomorrow", "நாளை", "morning")):
        return None
    candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _after(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip(" ?.!") if m and m.group(1).strip(" ?.!") else None


def route(text: str, available: set[str], now: datetime) -> tuple[str, dict[str, Any]] | None:
    t = text.lower().strip()

    def ok(name: str) -> bool:
        return name in available

    if ok("memory_save") and (m := re.match(r"^(?:please\s+)?(?:remember|note down|note)\s+(?:that\s+)?(.{3,})", t)):
        return "memory_save", {"content": text[m.start(1) :].strip(" ."), "kind": "fact"}
    if ok("memory_search") and (
        q := _after(
            r"(?:what did i (?:tell|say to) you about|do you remember|"
            r"what do you know about)\s+(.+)",
            text,
        )
    ):
        return "memory_search", {"query": q}
    if ok("reminder_create") and (m := re.search(r"remind me (?:to |about )?(.+)", t)):
        when = parse_when(t, now)
        body = re.sub(
            r"\b(tomorrow|today|tonight|day after tomorrow|in \d+ \w+|at \d{1,2}(:\d{2})?\s*(am|pm)?|"
            r"(this )?(morning|evening|afternoon))\b",
            "",
            text[m.start(1) :],
            flags=re.IGNORECASE,
        )
        if when:
            return "reminder_create", {
                "message": " ".join(body.split()).strip(" .") or "Reminder",
                "remind_at": when.strftime("%Y-%m-%dT%H:%M"),
            }
    if ok("briefing_generate") and re.search(r"briefing|brief me|my day|good morning", t):
        return "briefing_generate", {}
    if ok("gmail_unread") and re.search(r"\b(e-?mails?|inbox|gmail|mails?)\b", t):
        if ok("gmail_search") and (q := _after(r"(?:emails?|mails?) (?:from|about) (.+)", text)):
            return "gmail_search", {"query": q}
        return "gmail_unread", {}
    if ok("places_nearby") and re.search(r"near|nearby|nearest|closest|around|find (a|an|the)|அருகில்", t):
        for category, pattern in PLACE_WORDS.items():
            if re.search(pattern, t):
                place = _after(r"(?:near|in|around)\s+(?!me\b|my\b|here\b|by\b)([a-z][\w ,]+)$", text)
                return "places_nearby", {"category": category, **({"place": place} if place else {})}
    if ok("weather_forecast") and re.search(r"weather|temperature|forecast|rain|umbrella|hot|cold|வானிலை|மழை", t):
        place = _after(r"\b(?:in|at|for)\s+([A-Za-z][\w ]+?)(?:\s+(?:today|tomorrow|this week|now))?[?.!]*$", text)
        days = 3 if re.search(r"week|tomorrow|next", t) else 1
        return "weather_forecast", {"days": days, **({"place": place} if place else {})}
    if ok("news_headlines") and re.search(r"news|headlines|updates|செய்தி", t):
        category = None
        for cat, pattern in {
            "ai": r"\bai\b|artificial intelligence",
            "technology": r"tech",
            "business": r"business|market",
            "science": r"science",
            "india": r"india|tamil nadu",
            "world": r"world|international",
        }.items():
            if re.search(pattern, t):
                category = cat
                break
        return "news_headlines", ({"category": category} if category else {})
    if ok("youtube_search") and re.search(r"youtube|video|tutorial", t):
        q = (
            _after(r"(?:youtube|videos?)\s+(?:for|about|on)\s+(.+)", text)
            or _after(r"search youtube (?:for )?(.+)", text)
            or text
        )
        return "youtube_search", {"query": q[:200]}
    if ok("music_search") and re.search(r"\b(play|music|songs?|playlist)\b|பாடல்", t):
        q = _after(r"play (?:some |me )?(.+)", text) or _after(r"(.+?)\s+(?:music|songs?)", text) or "relaxing"
        q = re.sub(r"\b(music|songs?)\b", "", q, flags=re.IGNORECASE).strip() or "relaxing"
        return "music_search", {"query": q}
    if ok("directions_link") and (dest := _after(r"(?:directions|route|navigate|way) to (.+)", text)):
        return "directions_link", {"destination": dest}
    if ok("vault_list_items") and re.search(r"\bvault\b|my secrets|saved passwords", t):
        return "vault_list_items", {}
    if ok("automation_list") and re.search(r"my (reminders|automations)", t):
        return "automation_list", {}
    return None


class OfflineIntentRouter(LLMProvider):
    name = "offline"
    model = "intent-router-v1"
    offline = True

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: TokenCallback | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        last_user = max((i for i, msg in enumerate(messages) if msg.role == "user"), default=-1)
        tool_msgs = [msg for msg in messages[last_user + 1 :] if msg.role == "tool"]
        if tool_msgs:
            parts = []
            for msg in tool_msgs:
                try:
                    payload = json.loads(msg.content)
                    parts.append(str(payload.get("message") or ""))
                except (json.JSONDecodeError, AttributeError):
                    parts.append(msg.content[:300])
            text = " ".join(p for p in parts if p) or "Done."
            return await self._reply(text, on_token)
        if last_user < 0:
            return await self._reply(HELP, on_token)
        now, _tz = _now(messages)
        available = {t["function"]["name"] for t in tools or []}
        intent = route(messages[last_user].content, available, now)
        if intent is None:
            return await self._reply(HELP, on_token)
        name, args = intent
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(id=uuid.uuid4().hex[:12], name=name, arguments=args)],
            provider=self.name,
            model=self.model,
            offline=True,
        )

    async def _reply(self, text: str, on_token: TokenCallback | None) -> LLMResponse:
        if on_token:
            await on_token(text)
        return LLMResponse(content=text, tool_calls=[], provider=self.name, model=self.model, offline=True)
