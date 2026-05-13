import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse, urlunparse


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


class Collector:
    """Protocol - subclasses implement collect()."""
    async def collect(self) -> list[CollectedItem]:
        raise NotImplementedError


def canonical_url(url: str | None) -> str | None:
    """Normalize URL: lowercase scheme+host, remove tracking params, remove fragment."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        # normalize scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        # rebuild without fragment, keep path/query
        normalized = urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))
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
