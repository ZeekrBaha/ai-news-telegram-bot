import asyncio
import calendar
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from src.collectors.base import (
    CollectedItem,
    Collector,
    canonical_url,
    compute_title_hash,
    compute_url_hash,
    extract_media_from_entry,
    sha256_text,
    strip_html,
    truncate_content,
)
from src.config import Settings

logger = logging.getLogger(__name__)


class RssCollector(Collector):
    def __init__(self, settings: Settings, sources: list[dict]):
        self.settings = settings
        self.sources = sources  # list of {"name": ..., "url": ...}

    async def collect(self) -> list[CollectedItem]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = [self._fetch_feed(client, src) for src in self.sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        items = []
        for src, result in zip(self.sources, results):
            if isinstance(result, Exception):
                logger.warning("Feed %s failed: %s", src["name"], result)
                continue
            items.extend(result)
        return items

    async def _fetch_feed(self, client: httpx.AsyncClient, source: dict) -> list[CollectedItem]:
        response = await client.get(source["url"])
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        items = []
        for entry in feed.entries:
            item = self._parse_entry(entry, source["name"])
            if item is not None:
                items.append(item)
        return items

    def _parse_entry(self, entry: dict, source_name: str) -> CollectedItem | None:
        title = entry.get("title", "").strip()
        if not title:
            return None

        url = entry.get("link") or entry.get("url")

        # Date parsing: use calendar.timegm for UTC-safe conversion
        published_at = None
        if entry.get("published_parsed"):
            try:
                published_at = datetime.fromtimestamp(
                    calendar.timegm(entry.published_parsed), tz=timezone.utc
                )
            except Exception:
                pass
        if published_at is None:
            published_at = datetime.now(timezone.utc)

        # Content
        content_raw = ""
        if entry.get("content"):
            content_raw = entry["content"][0].get("value", "")
        elif entry.get("summary"):
            content_raw = entry.get("summary", "")
        content = truncate_content(strip_html(content_raw))

        # Stable ID: prefer entry id, fallback to URL, fallback to title hash
        source_item_id = entry.get("id") or url or sha256_text(title)

        url_hash = compute_url_hash(url, "rss", source_name, source_item_id)
        title_hash = compute_title_hash(title)

        media_url, media_type = extract_media_from_entry(entry)

        return CollectedItem(
            source_type="rss",
            source_name=source_name,
            source_item_id=source_item_id,
            url=url,
            canonical_url=canonical_url(url),
            url_hash=url_hash,
            title_hash=title_hash,
            title=title,
            content=content,
            published_at=published_at,
            raw=dict(entry),
            media_url=media_url,
            media_type=media_type,
        )
