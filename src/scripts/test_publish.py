"""One-off script: fetch 5 processed items from Supabase and publish to Telegram."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.config import get_settings
from src.database.client import get_client
from src.publisher.formatter import format_digest
from src.publisher.telegram_bot import publish_digest


async def main() -> None:
    settings = get_settings()
    db = get_client(settings)

    # Fetch 5 processed items joined with their URLs via ranked_items -> raw_items
    result = (
        db.table("processed_items")
        .select("title_ru, bullets_ru, why_it_matters_ru, hashtags, ranked_items(rank, raw_items(url))")
        .limit(5)
        .execute()
    )

    rows = result.data
    if not rows:
        print("No processed items found in DB.")
        return

    items = []
    for row in rows:
        ranked = row.get("ranked_items") or {}
        raw = ranked.get("raw_items") or {}
        items.append({
            "title_ru": row["title_ru"],
            "bullets_ru": row["bullets_ru"],
            "why_it_matters_ru": row.get("why_it_matters_ru", ""),
            "hashtags": row.get("hashtags") or [],
            "url": raw.get("url"),
            "rank": ranked.get("rank", 99),
        })

    items.sort(key=lambda x: x["rank"])

    digest, _ = format_digest(items, min_items=1)
    print("--- DIGEST PREVIEW ---")
    print(digest)
    print(f"--- {len(digest)} chars ---")

    message_id = await publish_digest(
        bot_token=settings.telegram_bot_token,
        channel_id=settings.telegram_channel_id,
        text=digest,
    )
    print(f"Published! message_id={message_id}")


asyncio.run(main())
