import hashlib
import html
import logging
from datetime import date
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_TELEGRAM_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024


def is_valid_url(url: str | None) -> bool:
    """Check if URL is safe to put in an href attribute."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def format_digest(
    items: list[dict],  # each has: title_ru, bullets_ru, why_it_matters_ru, hashtags, url, rank
    channel_date: date | None = None,
    min_items: int = 3,
) -> tuple[str, str]:
    """
    Build Telegram HTML digest string.

    Args:
        items: list of processed item dicts, sorted by rank (rank 1 first)
        channel_date: date for the header, defaults to today
        min_items: minimum items required (raises ValueError if we can't meet it)

    Returns:
        (digest_text, content_hash) tuple

    Raises:
        ValueError: if digest cannot be reduced to <= MAX_TELEGRAM_LENGTH while keeping min_items
    """
    if channel_date is None:
        channel_date = date.today()

    date_str = channel_date.strftime("%d.%m.%Y")

    def build_digest(current_items: list[dict]) -> str:
        parts = [f"<b>🤖 AI Дайджест {date_str}</b>\n"]

        for i, item in enumerate(current_items, 1):
            title_ru = html.escape(item["title_ru"])
            url = item.get("url")

            if is_valid_url(url):
                title_line = f'{i}. <a href="{html.escape(url)}">{title_ru}</a>'
            else:
                title_line = f"{i}. <b>{title_ru}</b>"

            parts.append(f"\n{title_line}")

            for bullet in item["bullets_ru"]:
                parts.append(f"• {html.escape(bullet)}")

            why = item.get("why_it_matters_ru", "")
            if why:
                parts.append(f"\n<i>💡 {html.escape(why)}</i>")

        # Deduped hashtags from all items
        seen_tags: set[str] = set()
        all_tags = []
        for item in current_items:
            for tag in item.get("hashtags", []):
                tag_lower = tag.lower()
                if tag_lower not in seen_tags:
                    seen_tags.add(tag_lower)
                    all_tags.append(tag)

        if all_tags:
            parts.append(f"\n{' '.join(all_tags)}")

        return "\n".join(parts)

    # Step 1: Try full digest
    working_items = list(items)
    digest = build_digest(working_items)

    if len(digest) <= MAX_TELEGRAM_LENGTH:
        content_hash = hashlib.sha256(digest.encode("utf-8")).hexdigest()
        return digest, content_hash

    # Step 2: Shorten why_it_matters_ru
    shortened = []
    for item in working_items:
        new_item = dict(item)
        why = new_item.get("why_it_matters_ru", "")
        if len(why) > 100:
            new_item["why_it_matters_ru"] = why[:97] + "..."
        shortened.append(new_item)

    digest = build_digest(shortened)
    if len(digest) <= MAX_TELEGRAM_LENGTH:
        content_hash = hashlib.sha256(digest.encode("utf-8")).hexdigest()
        return digest, content_hash

    # Step 3: Shorten bullets
    shortened2 = []
    for item in shortened:
        new_item = dict(item)
        new_item["bullets_ru"] = [
            (b[:97] + "...") if len(b) > 100 else b
            for b in new_item["bullets_ru"]
        ]
        shortened2.append(new_item)

    digest = build_digest(shortened2)
    if len(digest) <= MAX_TELEGRAM_LENGTH:
        content_hash = hashlib.sha256(digest.encode("utf-8")).hexdigest()
        return digest, content_hash

    # Step 4: Remove lowest-ranked items (items are sorted rank 1 first, so remove from end)
    current = list(shortened2)
    while len(current) > min_items:
        current.pop()  # remove last (lowest rank)
        digest = build_digest(current)
        if len(digest) <= MAX_TELEGRAM_LENGTH:
            content_hash = hashlib.sha256(digest.encode("utf-8")).hexdigest()
            return digest, content_hash

    # Final attempt with min_items
    digest = build_digest(current)
    if len(digest) <= MAX_TELEGRAM_LENGTH:
        content_hash = hashlib.sha256(digest.encode("utf-8")).hexdigest()
        return digest, content_hash

    raise ValueError(
        f"Digest is {len(digest)} chars, exceeds {MAX_TELEGRAM_LENGTH} even with {min_items} items. "
        "Refusing to publish."
    )


def format_hero_caption(
    lead_item: dict,
    channel_date: date | None = None,
) -> str:
    """
    Build a short caption that sits under the hero photo.

    Caption layout:
        <b>🤖 AI Дайджест {date}</b>

        Главная история: <a href="...">{title}</a>

    Hard-capped at MAX_CAPTION_LENGTH (1024 chars). If the formatted caption
    overflows, the title is trimmed with an ellipsis until it fits.
    """
    if channel_date is None:
        channel_date = date.today()

    date_str = channel_date.strftime("%d.%m.%Y")
    header = f"<b>🤖 AI Дайджест {date_str}</b>"

    title = lead_item.get("title_ru", "").strip()
    url = lead_item.get("url")

    def assemble(t: str) -> str:
        safe_title = html.escape(t)
        if is_valid_url(url):
            title_line = f'Главная история: <a href="{html.escape(url)}">{safe_title}</a>'
        else:
            title_line = f"Главная история: <b>{safe_title}</b>"
        return f"{header}\n\n{title_line}"

    caption = assemble(title)
    if len(caption) <= MAX_CAPTION_LENGTH:
        return caption

    # Shrink the raw title until the rendered caption fits. Title gets an ellipsis.
    stem = title
    while len(stem) > 10:
        stem = stem[:-5].rstrip()
        candidate = assemble(stem + "…")
        if len(candidate) <= MAX_CAPTION_LENGTH:
            return candidate

    # Last resort: hard-cut the rendered caption.
    return assemble(stem + "…")[:MAX_CAPTION_LENGTH]
