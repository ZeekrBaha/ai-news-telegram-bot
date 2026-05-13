import logging
import traceback
from datetime import datetime, timedelta, timezone

from src.ai.client import get_ai_client
from src.ai.ranker import rank_items
from src.ai.summarizer import summarize_item
from src.ai.translator import translate_item
from src.collectors.base import CollectedItem
from src.collectors.rss import RssCollector
from src.collectors.telegram import TelegramCollector
from src.config import Settings, load_sources
from src.database.client import get_client
from src.database.repository import (
    create_pending_digest,
    create_run,
    finalize_run,
    find_existing_hashes,
    insert_raw_items,
    mark_digest_failed,
    mark_digest_published,
    record_processed_items,
    record_ranked_items,
)
from src.publisher.formatter import format_digest
from src.publisher.telegram_bot import publish_digest

logger = logging.getLogger(__name__)


async def run_daily(settings: Settings, dry_run: bool = False) -> None:
    """
    Main daily pipeline. Creates a run row, collects, ranks, summarizes,
    translates, formats, and publishes a digest.

    On any failure, finalizes the run as failed and re-raises.
    """
    db = get_client(settings)
    ai = get_ai_client(settings)
    sources = load_sources()

    run_id = create_run(db)
    logger.info("Started run %s (dry_run=%s)", run_id, dry_run)

    digest_id = None

    try:
        # --- Step 1: Collect ---
        rss_collector = RssCollector(
            settings=settings,
            sources=[{"name": s.name, "url": s.url} for s in sources.rss],
        )

        telegram_channels = sources.telegram_channels

        candidates: list[CollectedItem] = []

        rss_items = await rss_collector.collect()
        candidates.extend(rss_items)
        logger.info("RSS collected: %d items", len(rss_items))

        if telegram_channels:
            try:
                tg_collector = TelegramCollector(
                    settings=settings,
                    channels=telegram_channels,
                    max_age_hours=settings.max_age_hours,
                )
                tg_items = await tg_collector.collect()
                candidates.extend(tg_items)
                logger.info("Telegram collected: %d items", len(tg_items))
            except Exception as e:
                logger.error("Telegram collection failed, continuing RSS-only: %s", e)

        items_collected = len(candidates)

        # --- Step 2: Filter by age ---
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.max_age_hours)
        candidates = [c for c in candidates if c.published_at >= cutoff]
        logger.info("After age filter: %d items", len(candidates))

        # --- Step 3: Pre-insert dedupe ---
        url_hashes = [c.url_hash for c in candidates]
        title_hashes = [c.title_hash for c in candidates]
        existing = find_existing_hashes(db, url_hashes, title_hashes)

        new_candidates = [
            c for c in candidates
            if c.url_hash not in existing.url_hashes
            and c.title_hash not in existing.title_hashes
        ]
        logger.info(
            "After dedup: %d new items (filtered %d duplicates)",
            len(new_candidates),
            len(candidates) - len(new_candidates),
        )

        items_after_dedup = len(new_candidates)

        # --- Step 4: Insert raw items ---
        raw_rows = insert_raw_items(
            db,
            run_id,
            [
                {
                    "source_type": c.source_type,
                    "source_name": c.source_name,
                    "source_item_id": c.source_item_id,
                    "url": c.url,
                    "canonical_url": c.canonical_url,
                    "url_hash": c.url_hash,
                    "title_hash": c.title_hash,
                    "title": c.title,
                    "content": c.content,
                    "published_at": c.published_at,
                    "raw": c.raw,
                }
                for c in new_candidates
            ],
        )

        # Map url_hash -> raw row id for later steps
        raw_id_by_hash = {row.url_hash: row.id for row in raw_rows}

        # --- Step 5: Check minimum ---
        if items_after_dedup < settings.min_digest_items:
            logger.info(
                "Only %d new items, need %d. Marking run skipped.",
                items_after_dedup,
                settings.min_digest_items,
            )
            finalize_run(
                db, run_id, "skipped",
                items_collected=items_collected,
                items_after_dedup=items_after_dedup,
            )
            return

        # --- Step 6: Rank ---
        ranked_choices = await rank_items(
            ai, settings.openai_model, new_candidates, top_n=settings.digest_top_n
        )
        logger.info("Ranked: %d items selected", len(ranked_choices))

        # Map ranked choice id (url_hash) back to CollectedItem
        item_by_hash = {c.url_hash: c for c in new_candidates}
        selected_items = []
        for choice in ranked_choices:
            item = item_by_hash.get(choice.id)
            if item:
                selected_items.append((choice, item))

        # Record ranked items
        ranked_rows = record_ranked_items(
            db,
            run_id,
            [
                {
                    "raw_item_id": raw_id_by_hash[choice.id],
                    "rank": choice.rank,
                    "score": choice.score,
                    "reasoning": choice.reasoning,
                }
                for choice, _ in selected_items
                if choice.id in raw_id_by_hash
            ],
        )

        # Build rank -> ranked_item db id map
        ranked_id_by_rank = {row["rank"]: row["id"] for row in ranked_rows}

        # --- Step 7: Summarize and translate ---
        processed = []
        for choice, item in selected_items:
            try:
                summary_en = await summarize_item(ai, settings.openai_model, item)
                translated = await translate_item(
                    ai, settings.openai_model, item.title, summary_en, item.url
                )
                processed.append({
                    "choice": choice,
                    "item": item,
                    "summary_en": summary_en,
                    "translated": translated,
                })
            except Exception as e:
                logger.warning("Failed to process item '%s': %s", item.title, e)
                # If we have enough other items, skip this one
                if len(processed) + (len(selected_items) - len(processed) - 1) >= settings.min_digest_items:
                    logger.info("Dropping failed item, enough remaining")
                    continue
                else:
                    # Not enough items if we skip, re-raise
                    raise

        if len(processed) < settings.min_digest_items:
            raise ValueError(
                f"Only {len(processed)} items processed successfully, need {settings.min_digest_items}"
            )

        # Record processed items
        processed_rows_input = [
            {
                "ranked_item_id": ranked_id_by_rank[p["choice"].rank],
                "summary_en": p["summary_en"],
                "title_ru": p["translated"].title_ru,
                "bullets_ru": p["translated"].bullets_ru,
                "why_it_matters_ru": p["translated"].why_it_matters_ru,
                "hashtags": p["translated"].hashtags,
            }
            for p in processed
            if p["choice"].rank in ranked_id_by_rank
        ]
        record_processed_items(db, processed_rows_input)

        # --- Step 8: Format digest ---
        digest_items = [
            {
                "title_ru": p["translated"].title_ru,
                "bullets_ru": p["translated"].bullets_ru,
                "why_it_matters_ru": p["translated"].why_it_matters_ru,
                "hashtags": p["translated"].hashtags,
                "url": p["item"].url,
                "rank": p["choice"].rank,
            }
            for p in processed
        ]
        # Sort by rank
        digest_items.sort(key=lambda x: x["rank"])

        digest_text, content_hash = format_digest(
            digest_items,
            min_items=settings.min_digest_items,
        )

        # --- Step 9: Dry run path ---
        if dry_run:
            logger.info("DRY RUN - digest preview:\n%s", digest_text)
            print("\n" + "=" * 60)
            print("DRY RUN DIGEST PREVIEW")
            print("=" * 60)
            print(digest_text)
            print("=" * 60 + "\n")
            finalize_run(
                db, run_id, "success",
                items_collected=items_collected,
                items_after_dedup=items_after_dedup,
                items_published=len(processed),
            )
            return

        # --- Step 10: Create pending digest row ---
        item_ids = [raw_id_by_hash[p["item"].url_hash] for p in processed if p["item"].url_hash in raw_id_by_hash]
        digest_id = create_pending_digest(
            db,
            run_id=run_id,
            channel_id=settings.telegram_channel_id,
            content_hash=content_hash,
            item_ids=item_ids,
        )
        logger.info("Created pending digest %s", digest_id)

        # --- Step 11: Publish ---
        message_id = await publish_digest(
            bot_token=settings.telegram_bot_token,
            channel_id=settings.telegram_channel_id,
            text=digest_text,
        )
        logger.info("Published digest, message_id=%s", message_id)

        # --- Step 12: Mark published ---
        mark_digest_published(db, digest_id, message_id)

        # --- Step 13: Finalize run ---
        finalize_run(
            db, run_id, "success",
            items_collected=items_collected,
            items_after_dedup=items_after_dedup,
            items_published=len(processed),
        )
        logger.info("Run %s completed successfully", run_id)

    except Exception as e:
        error_text = traceback.format_exc()
        logger.error("Run %s failed: %s", run_id, error_text)

        # Mark digest failed if it was created
        if digest_id is not None:
            try:
                mark_digest_failed(db, digest_id, str(e))
            except Exception as inner:
                logger.error("Failed to mark digest failed: %s", inner)

        # Finalize run as failed
        try:
            finalize_run(db, run_id, "failed", error=error_text)
        except Exception as inner:
            logger.error("Failed to finalize run: %s", inner)

        raise
