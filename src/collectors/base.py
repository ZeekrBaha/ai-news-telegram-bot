import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

MediaType = Literal["photo", "animation", "video"]


@dataclass(frozen=True)
class CollectedItem:
    source_type: str          # "rss" | "telegram"
    source_name: str
    source_item_id: str       # stable id
    url: str | None
    canonical_url: str | None
    url_hash: str             # sha256(canonical_url or source identity)
    title_hash: str           # sha256(normalized title)
    title: str
    content: str              # plain text, truncated
    published_at: datetime
    raw: dict
    media_url: str | None = field(default=None)
    media_type: MediaType | None = field(default=None)
    # ISO 639-1 language code of the source. "en" by default; "ru" sources skip
    # the translator since the article is already in Russian.
    language: str = field(default="en")


class Collector:
    """Protocol - subclasses implement collect()."""
    async def collect(self) -> list[CollectedItem]:
        raise NotImplementedError


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "msclkid",
    "ref",
    "spm",
}


def canonical_url(url: str | None) -> str | None:
    """Normalize URL for dedupe: lowercase origin, drop tracking params and fragment."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        if path != "/":
            path = path.rstrip("/")

        clean_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            key_lower = key.lower()
            if key_lower in TRACKING_QUERY_PARAMS:
                continue
            if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
                continue
            clean_query.append((key, value))

        query = urlencode(clean_query, doseq=True)
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
        return normalized
    except Exception:
        return url


def normalize_title(title: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for dedup comparison."""
    t = title.lower()
    t = re.sub(r'[^\w\s]', '', t)  # remove punctuation
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_url_hash(
    url: str | None,
    source_type: str,
    source_name: str,
    source_item_id: str,
) -> str:
    """Compute url_hash from canonical URL when available, else from source identity."""
    canon = canonical_url(url)
    if canon:
        return sha256_text(canon)
    # For items without URL (Telegram private, etc.)
    identity = f"{source_type}:{source_name}:{source_item_id}"
    return sha256_text(identity)


def compute_title_hash(title: str) -> str:
    return sha256_text(normalize_title(title))


def strip_html(html: str) -> str:
    """Remove HTML tags, return plain text."""
    return re.sub(r'<[^>]+>', '', html)


MAX_CONTENT_CHARS = 2000

def truncate_content(text: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


# Patterns hinting an image URL is a small thumbnail and not worth using as hero.
_THUMBNAIL_HINTS = (
    "thumb", "thumbnail", "/small/", "-150x", "-300x", "_150x", "_300x",
    "icon", "avatar", "favicon",
)


def _looks_like_thumbnail(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in _THUMBNAIL_HINTS)


def _classify_media_type(url: str, mime: str | None = None) -> MediaType | None:
    """Map a URL/MIME to a Telegram media type. Only 'photo' is wired up today."""
    if mime:
        mime_lower = mime.lower()
        if mime_lower.startswith("image/gif"):
            return "animation"
        if mime_lower.startswith("video/"):
            return "video"
        if mime_lower.startswith("image/"):
            return "photo"

    lower = url.lower().split("?")[0]
    if lower.endswith(".gif"):
        return "animation"
    if lower.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "photo"
    return None


def _first_inline_image(html_text: str) -> str | None:
    """Find the first <img src="..."> URL in HTML content."""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def extract_media_from_entry(entry: dict) -> tuple[str | None, MediaType | None]:
    """
    Pick the best hero media URL from a feedparser RSS entry.

    Walks four sources in priority order. Returns (url, type) on first hit,
    or (None, None) if nothing usable was found.
    """
    # 1. media_content — most reliable, used by TechCrunch / Wired / Verge / Ars / MITTR.
    for media in entry.get("media_content") or []:
        url = (media.get("url") or "").strip()
        if not url or _looks_like_thumbnail(url):
            continue
        media_type = _classify_media_type(url, media.get("type"))
        if media_type == "photo":
            return url, media_type

    # 2. media_thumbnail — common alternative; thumbnails are smaller but still usable.
    for thumb in entry.get("media_thumbnail") or []:
        url = (thumb.get("url") or "").strip()
        if not url:
            continue
        media_type = _classify_media_type(url)
        if media_type == "photo":
            return url, media_type

    # 3. enclosures — VentureBeat and friends.
    for enclosure in entry.get("enclosures") or []:
        url = (enclosure.get("href") or enclosure.get("url") or "").strip()
        if not url or _looks_like_thumbnail(url):
            continue
        media_type = _classify_media_type(url, enclosure.get("type"))
        if media_type == "photo":
            return url, media_type

    # 4. Inline <img> in summary or content body.
    bodies: list[str] = []
    if entry.get("summary"):
        bodies.append(entry["summary"])
    for content in entry.get("content") or []:
        value = content.get("value") if isinstance(content, dict) else None
        if value:
            bodies.append(value)
    for body in bodies:
        inline = _first_inline_image(body)
        if not inline or _looks_like_thumbnail(inline):
            continue
        media_type = _classify_media_type(inline)
        if media_type == "photo":
            return inline, media_type

    return None, None
