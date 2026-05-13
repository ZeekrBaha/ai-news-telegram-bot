from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from supabase import Client

from src.database.models import ExistingHashes, RawItemRow


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO format datetime string to datetime object."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def create_run(client: Client) -> UUID:
    """Insert a new run with status='running', return its id."""
    result = client.table("runs").insert({"status": "running"}).execute()
    return UUID(result.data[0]["id"])


def finalize_run(
    client: Client,
    run_id: UUID,
    status: str,
    items_collected: int = 0,
    items_after_dedup: int = 0,
    items_published: int = 0,
    error: str | None = None,
) -> None:
    """Update run to terminal status with counts."""
    data: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "items_collected": items_collected,
        "items_after_dedup": items_after_dedup,
        "items_published": items_published,
    }
    if error is not None:
        data["error"] = error
    client.table("runs").update(data).eq("id", str(run_id)).execute()


def find_existing_hashes(
    client: Client,
    url_hashes: list[str],
    title_hashes: list[str],
) -> ExistingHashes:
    """Query raw_items for any matching url_hash or title_hash."""
    if not url_hashes and not title_hashes:
        return ExistingHashes(url_hashes=frozenset(), title_hashes=frozenset())

    existing_url_hashes: set[str] = set()
    existing_title_hashes: set[str] = set()

    if url_hashes:
        result = (
            client.table("raw_items").select("url_hash").in_("url_hash", url_hashes).execute()
        )
        existing_url_hashes = {row["url_hash"] for row in result.data}

    if title_hashes:
        result = (
            client.table("raw_items")
            .select("title_hash")
            .in_("title_hash", title_hashes)
            .execute()
        )
        existing_title_hashes = {row["title_hash"] for row in result.data}

    return ExistingHashes(
        url_hashes=frozenset(existing_url_hashes),
        title_hashes=frozenset(existing_title_hashes),
    )


def insert_raw_items(
    client: Client,
    run_id: UUID,
    items: list[dict],  # list of CollectedItem-like dicts
) -> list[RawItemRow]:
    """Insert items into raw_items and return inserted rows."""
    if not items:
        return []

    rows = []
    for item in items:
        rows.append(
            {
                "run_id": str(run_id),
                "source_type": item["source_type"],
                "source_name": item["source_name"],
                "source_item_id": item["source_item_id"],
                "url": item.get("url"),
                "canonical_url": item.get("canonical_url"),
                "url_hash": item["url_hash"],
                "title_hash": item["title_hash"],
                "title": item["title"],
                "content": item.get("content"),
                "published_at": (
                    item["published_at"].isoformat() if item.get("published_at") else None
                ),
                "raw": item.get("raw"),
            }
        )

    result = client.table("raw_items").insert(rows).execute()
    return [
        RawItemRow(
            id=UUID(r["id"]),
            run_id=UUID(r["run_id"]),
            source_type=r["source_type"],
            source_name=r["source_name"],
            source_item_id=r["source_item_id"],
            url_hash=r["url_hash"],
            title_hash=r["title_hash"],
            title=r["title"],
            url=r.get("url"),
            canonical_url=r.get("canonical_url"),
            content=r.get("content"),
            published_at=_parse_dt(r.get("published_at")),
        )
        for r in result.data
    ]


def record_ranked_items(
    client: Client,
    run_id: UUID,
    ranked_items: list[dict],  # each has raw_item_id, rank, score, reasoning
) -> list[dict]:
    """Insert ranked_items rows and return them."""
    if not ranked_items:
        return []
    rows = [
        {
            "raw_item_id": str(item["raw_item_id"]),
            "run_id": str(run_id),
            "rank": item["rank"],
            "score": item.get("score"),
            "reasoning": item.get("reasoning"),
        }
        for item in ranked_items
    ]
    result = client.table("ranked_items").insert(rows).execute()
    return result.data


def record_processed_items(
    client: Client,
    processed_items: list[dict],  # each has ranked_item_id, title_ru, bullets_ru, etc.
) -> list[dict]:
    """Insert processed_items rows."""
    if not processed_items:
        return []
    rows = [
        {
            "ranked_item_id": str(item["ranked_item_id"]),
            "summary_en": item.get("summary_en"),
            "title_ru": item["title_ru"],
            "bullets_ru": item["bullets_ru"],
            "why_it_matters_ru": item.get("why_it_matters_ru"),
            "hashtags": item.get("hashtags"),
            "validation_notes": item.get("validation_notes"),
        }
        for item in processed_items
    ]
    result = client.table("processed_items").insert(rows).execute()
    return result.data


def create_pending_digest(
    client: Client,
    run_id: UUID,
    channel_id: str,
    content_hash: str,
    item_ids: list[UUID],
) -> UUID:
    """Create a pending digest row before publishing."""
    result = client.table("digests").insert(
        {
            "run_id": str(run_id),
            "status": "pending",
            "content_hash": content_hash,
            "channel_id": channel_id,
            "item_ids": [str(iid) for iid in item_ids],
        }
    ).execute()
    return UUID(result.data[0]["id"])


def mark_digest_published(
    client: Client,
    digest_id: UUID,
    message_id: int,
) -> None:
    """Update digest to published with telegram message id."""
    client.table("digests").update(
        {
            "status": "published",
            "telegram_message_id": message_id,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", str(digest_id)).execute()


def mark_digest_failed(
    client: Client,
    digest_id: UUID,
    error: str,
) -> None:
    """Update digest to failed with error message."""
    client.table("digests").update(
        {
            "status": "failed",
            "error": error,
        }
    ).eq("id", str(digest_id)).execute()
