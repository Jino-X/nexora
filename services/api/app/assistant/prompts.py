"""System prompts. Kept short: every token is paid for on every turn (local or cloud)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

LANGUAGE_RULES = {
    "auto": "Reply in the language the user uses: English, Tamil (தமிழ்), or the same Tamil-English mix.",
    "en": "Reply in English unless the user explicitly asks for another language.",
    "ta": "Reply in Tamil (தமிழ்). Keep technical terms, names and brands in English where natural.",
}


def build_system_prompt(
    *,
    name: str | None,
    now_local: datetime,
    timezone: str,
    location_label: str | None,
    has_location: bool,
    language: str,
    style: str,
    channel: str,
    memories: list[dict[str, Any]],
) -> str:
    lines = [
        "You are Nexora, a friendly and capable personal AI assistant" + (f" for {name}." if name else "."),
        f"[context] now={now_local.isoformat(timespec='minutes')} tz={timezone} "
        f"weekday={now_local:%A} location={'shared' if has_location else 'unknown'}"
        + (f" ({location_label})" if location_label else ""),
        LANGUAGE_RULES.get(language, LANGUAGE_RULES["auto"]),
    ]
    if channel == "voice":
        lines.append(
            "Your reply will be spoken aloud: 1-3 short sentences, no markdown, lists, URLs or emojis. "
            "Say numbers and times naturally."
        )
    elif style == "detailed":
        lines.append("Give thorough, well-structured answers using short markdown sections when helpful.")
    else:
        lines.append("Be concise and direct. Use short markdown lists only when they help.")
    lines += [
        "Rules:",
        "- Use the provided tools for live data (weather, news, places, email, YouTube, music, reminders). "
        "Never invent news, emails, places, prices, links or tool results.",
        "- Rich results (maps, videos, articles) are shown to the user as cards, so summarise and don't paste "
        "long lists of links.",
        "- Sending email or WhatsApp messages needs the user's approval. If a tool returns approval_required, say "
        "it is waiting for their approval in the app.",
        "- If a tool fails or a service is not connected, explain briefly and suggest the fix.",
        "- Call memory_save only when the user asks you to remember something. Never store or repeat passwords, "
        "API keys or other secrets. You cannot read the vault's secret values.",
        "- Resolve relative dates ('tomorrow 9am') using the context time and timezone above.",
    ]
    if memories:
        lines.append("Things the user asked you to remember (use only if relevant):")
        lines += [f"- {mem['content']}" for mem in memories]
    return "\n".join(lines)


def conversation_title(text: str) -> str:
    title = " ".join(text.strip().split())
    return (title[:57] + "...") if len(title) > 60 else title or "New conversation"
