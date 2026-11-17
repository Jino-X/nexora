"""RSS news aggregation with duplicate detection and source attribution.

Only headlines, links, dates and the publisher's own summaries are shown, always linked back to the
source. Check each publisher's terms before commercial use."""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from pydantic import BaseModel

from app.integrations.base import TTLCache

logger = logging.getLogger("nexora.news")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "at", "by", "with", "as", "from"}


class NewsItem(BaseModel):
    id: str
    title: str
    link: str
    source: str
    category: str
    published_at: datetime | None = None
    summary: str | None = None
    image_url: str | None = None


def clean_text(value: str | None, limit: int = 320) -> str | None:
    if not value:
        return None
    # Strip tags, unescape entities, then strip again for entity-encoded markup (&lt;p&gt;).
    text = TAG_RE.sub(" ", html.unescape(TAG_RE.sub(" ", value)))
    text = WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "..."
    return text or None


def canonical_link(link: str) -> str:
    parts = urlsplit(link.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def title_tokens(title: str) -> set[str]:
    return {w for w in WORD_RE.findall(title.lower()) if w not in STOPWORDS and len(w) > 1}


def is_duplicate(a: set[str], b: set[str], threshold: float = 0.7) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


def dedupe(items: list[NewsItem], threshold: float = 0.7) -> list[NewsItem]:
    kept: list[NewsItem] = []
    links: set[str] = set()
    token_sets: list[set[str]] = []
    for item in items:
        link = canonical_link(item.link)
        tokens = title_tokens(item.title)
        if link in links or any(is_duplicate(tokens, t, threshold) for t in token_sets):
            continue
        links.add(link)
        token_sets.append(tokens)
        kept.append(item)
    return kept


def _published(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    for key in ("published", "updated"):
        if entry.get(key):
            try:
                dt = parsedate_to_datetime(entry[key])
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    return None


def _image(entry: Any) -> str | None:
    for media in entry.get("media_thumbnail") or entry.get("media_content") or []:
        url = media.get("url")
        if url and url.startswith("https://"):
            return url
    return None


def parse_feed(content: bytes, source: str, category: str) -> list[NewsItem]:
    parsed = feedparser.parse(content)
    items: list[NewsItem] = []
    for entry in parsed.entries[:40]:
        link = entry.get("link")
        title = clean_text(entry.get("title"), 300)
        if not link or not title or not link.startswith(("http://", "https://")):
            continue
        items.append(
            NewsItem(
                id=hashlib.sha256(canonical_link(link).encode()).hexdigest()[:16],
                title=title,
                link=link,
                source=source,
                category=category,
                published_at=_published(entry),
                summary=clean_text(entry.get("summary") or entry.get("description")),
                image_url=_image(entry),
            )
        )
    return items


class RSSNewsProvider:
    def __init__(
        self,
        http: httpx.AsyncClient,
        feeds: list[dict[str, str]],
        timeout: float = 10.0,
        user_agent: str = "Nexora/0.1 RSS reader",
    ) -> None:
        self.http = http
        self.feeds = feeds
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.5"}
        self.cache = TTLCache(ttl_seconds=900, max_items=128)

    @property
    def categories(self) -> list[str]:
        return sorted({f["category"] for f in self.feeds})

    async def _fetch_feed(self, feed: dict[str, str]) -> list[NewsItem]:
        if (cached := self.cache.get(feed["url"])) is not None:
            return cached
        try:
            res = await self.http.get(feed["url"], timeout=self.timeout, headers=self.headers, follow_redirects=True)
            res.raise_for_status()
            items = await asyncio.to_thread(parse_feed, res.content, feed["name"], feed["category"])
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("feed fetch failed: %s (%s)", feed["name"], type(exc).__name__)
            return []
        self.cache.set(feed["url"], items)
        return items

    async def headlines(
        self, categories: list[str] | None = None, limit: int = 20, query: str | None = None
    ) -> list[NewsItem]:
        wanted = {c.lower() for c in categories} if categories else None
        feeds = [f for f in self.feeds if wanted is None or f["category"] in wanted]
        results = await asyncio.gather(*(self._fetch_feed(f) for f in feeds))
        items = [item for batch in results for item in batch]
        if query:
            q = title_tokens(query)
            items = [i for i in items if q & title_tokens(f"{i.title} {i.summary or ''}")]
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        items.sort(key=lambda i: i.published_at or epoch, reverse=True)
        return dedupe(items)[: max(1, min(limit, 60))]
