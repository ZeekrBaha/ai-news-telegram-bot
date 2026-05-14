"""Tests for the pipeline orchestrator (src/pipeline.py)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.pipeline import run_daily
from src.collectors.base import CollectedItem
from src.pipeline import _apply_source_filters, _dedupe_current_batch


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_collected_item(url_hash: str = "hash1", title_hash: str = "thash1"):
    """Return a minimal CollectedItem-like MagicMock."""
    item = MagicMock()
    item.source_type = "rss"
    item.source_name = "source"
    item.source_item_id = url_hash
    item.url_hash = url_hash
    item.title_hash = title_hash
    item.url = f"https://example.com/{url_hash}"
    item.canonical_url = item.url
    item.published_at = datetime.now(timezone.utc)
    item.title = f"Title {url_hash}"
    item.content = f"AI content about OpenAI and LLMs for {url_hash}"
    item.raw = {}
    return item


def _make_choice(rank: int, url_hash: str):
    choice = MagicMock()
    choice.id = url_hash
    choice.rank = rank
    choice.score = 0.9
    choice.reasoning = "relevant"
    return choice


def _make_translated():
    t = MagicMock()
    t.title_ru = "Заголовок"
    t.bullets_ru = ["Пункт 1", "Пункт 2"]
    t.why_it_matters_ru = "Важно потому что..."
    t.hashtags = ["#ИИ", "#Технологии"]
    return t


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.openai_model = "gpt-4o-mini"
    s.max_age_hours = 36
    s.min_digest_items = 3
    s.digest_top_n = 5
    s.telegram_channel_id = "@test_channel"
    s.telegram_bot_token = "test_token"
    s.supabase_url = "https://test.supabase.co"
    s.supabase_service_key = "test_key"
    s.telegram_channels = []
    # Hero-media defaults — existing tests exercise the text-only publish_digest path.
    s.enable_hero_media = False
    s.default_hero_path = "assets/default_hero.png"
    return s


def _make_sources_mock(telegram_channels=None):
    """Return a sources mock with empty telegram_channels by default."""
    sources = MagicMock()
    sources.rss = [MagicMock(name="TechCrunch", url="https://feeds.tc.com")]
    sources.telegram_channels = telegram_channels or []
    sources.filters = {}
    return sources


def _make_raw_row(url_hash: str, row_id=None):
    row = MagicMock()
    row.url_hash = url_hash
    row.id = row_id or str(uuid4())
    return row


def _make_ranked_rows(rank: int, ranked_id=None):
    """Return a list of one dict mimicking a ranked_item DB row."""
    return [{"rank": rank, "id": ranked_id or str(uuid4())}]


# All patches needed for the pipeline
_PATCHES = {
    "get_client": "src.pipeline.get_client",
    "get_ai_client": "src.pipeline.get_ai_client",
    "load_sources": "src.pipeline.load_sources",
    "RssCollector": "src.pipeline.RssCollector",
    "TelegramCollector": "src.pipeline.TelegramCollector",
    "rank_items": "src.pipeline.rank_items",
    "summarize_item": "src.pipeline.summarize_item",
    "translate_item": "src.pipeline.translate_item",
    "publish_digest": "src.pipeline.publish_digest",
    "create_run": "src.pipeline.create_run",
    "finalize_run": "src.pipeline.finalize_run",
    "find_existing_hashes": "src.pipeline.find_existing_hashes",
    "insert_raw_items": "src.pipeline.insert_raw_items",
    "record_ranked_items": "src.pipeline.record_ranked_items",
    "record_processed_items": "src.pipeline.record_processed_items",
    "create_pending_digest": "src.pipeline.create_pending_digest",
    "mark_digest_published": "src.pipeline.mark_digest_published",
    "mark_digest_failed": "src.pipeline.mark_digest_failed",
    "format_digest": "src.pipeline.format_digest",
}


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

def test_current_batch_dedupe_keeps_newest_unique_hashes():
    older = CollectedItem(
        source_type="rss",
        source_name="a",
        source_item_id="1",
        url="https://example.com/1",
        canonical_url="https://example.com/1",
        url_hash="same-url",
        title_hash="same-title",
        title="Older",
        content="AI story content",
        published_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        raw={},
    )
    newer = CollectedItem(
        source_type="rss",
        source_name="b",
        source_item_id="2",
        url="https://example.com/2",
        canonical_url="https://example.com/2",
        url_hash="same-url",
        title_hash="other-title",
        title="Newer",
        content="AI story content",
        published_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        raw={},
    )

    assert _dedupe_current_batch([older, newer]) == [newer]


def test_apply_source_filters_enforces_keywords_and_content_length():
    keep = _make_collected_item("keep", "keep-title")
    drop_short = _make_collected_item("short", "short-title")
    drop_short.content = "AI"
    drop_keyword = _make_collected_item("boring", "boring-title")
    drop_keyword.title = "Cooking update"
    drop_keyword.content = "A long enough item without matching terms"

    result = _apply_source_filters(
        [keep, drop_short, drop_keyword],
        {"keywords_include": ["OpenAI"], "min_content_chars": 20},
    )

    assert result == [keep]


# ---------------------------------------------------------------------------
# Test 1: dry_run=True never calls publish_digest
# ---------------------------------------------------------------------------

def test_dry_run_never_publishes(mock_settings):
    """publish_digest must NOT be called when dry_run=True."""
    run_id = str(uuid4())
    items = [_make_collected_item(f"h{i}", f"t{i}") for i in range(5)]
    choices = [_make_choice(i + 1, f"h{i}") for i in range(5)]
    raw_rows = [_make_raw_row(f"h{i}") for i in range(5)]
    ranked_rows_flat = [{"rank": i + 1, "id": str(uuid4())} for i in range(5)]

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run") as mock_finalize, \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=raw_rows), \
         patch("src.pipeline.record_ranked_items", return_value=ranked_rows_flat), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest"), \
         patch("src.pipeline.mark_digest_published"), \
         patch("src.pipeline.mark_digest_failed"), \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=choices)), \
         patch("src.pipeline.summarize_item", new=AsyncMock(return_value="summary")), \
         patch("src.pipeline.translate_item", new=AsyncMock(return_value=_make_translated())), \
         patch("src.pipeline.publish_digest", new=AsyncMock(return_value=42)) as mock_publish, \
         patch("src.pipeline.format_digest", return_value=("digest text", "chash123")):

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=items)
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            asyncio.run(run_daily(mock_settings, dry_run=True))

    mock_publish.assert_not_called()
    mock_finalize.assert_called_once_with(
        mock_finalize.call_args[0][0],  # db
        run_id,
        "success",
        items_collected=5,
        items_after_dedup=5,
        items_published=5,
    )


# ---------------------------------------------------------------------------
# Test 2: Too few items → run marked as "skipped"
# ---------------------------------------------------------------------------

def test_too_few_items_marks_run_skipped(mock_settings):
    """When 0 items are collected, finalize_run should be called with status='skipped'."""
    run_id = str(uuid4())

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run") as mock_finalize, \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=[]), \
         patch("src.pipeline.record_ranked_items"), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest"), \
         patch("src.pipeline.mark_digest_published"), \
         patch("src.pipeline.mark_digest_failed"), \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=[])), \
         patch("src.pipeline.publish_digest", new=AsyncMock()) as mock_publish:

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=[])
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            asyncio.run(run_daily(mock_settings, dry_run=False))

    # finalize_run called with "skipped"
    mock_finalize.assert_called_once()
    call_args = mock_finalize.call_args
    assert call_args[0][2] == "skipped", f"Expected 'skipped', got {call_args[0][2]!r}"

    # publish should never have been called
    mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: publish_digest failure marks digest failed and run failed
# ---------------------------------------------------------------------------

def test_publish_failure_marks_digest_and_run_failed(mock_settings):
    """When publish_digest raises, mark_digest_failed and finalize_run('failed') must be called."""
    run_id = str(uuid4())
    digest_id = str(uuid4())

    items = [_make_collected_item(f"h{i}", f"t{i}") for i in range(5)]
    choices = [_make_choice(i + 1, f"h{i}") for i in range(5)]
    raw_rows = [_make_raw_row(f"h{i}") for i in range(5)]
    ranked_rows_flat = [{"rank": i + 1, "id": str(uuid4())} for i in range(5)]

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run") as mock_finalize, \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=raw_rows), \
         patch("src.pipeline.record_ranked_items", return_value=ranked_rows_flat), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest", return_value=digest_id), \
         patch("src.pipeline.mark_digest_published"), \
         patch("src.pipeline.mark_digest_failed") as mock_mark_failed, \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=choices)), \
         patch("src.pipeline.summarize_item", new=AsyncMock(return_value="summary")), \
         patch("src.pipeline.translate_item", new=AsyncMock(return_value=_make_translated())), \
         patch("src.pipeline.publish_digest", new=AsyncMock(side_effect=RuntimeError("Telegram down"))) as mock_publish, \
         patch("src.pipeline.format_digest", return_value=("digest text", "chash123")):

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=items)
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            with pytest.raises(RuntimeError, match="Telegram down"):
                asyncio.run(run_daily(mock_settings, dry_run=False))

    # publish was attempted
    mock_publish.assert_called_once()

    # digest must be marked failed
    mock_mark_failed.assert_called_once()
    fail_args = mock_mark_failed.call_args[0]
    assert fail_args[1] == digest_id, f"Expected digest_id={digest_id!r}, got {fail_args[1]!r}"

    # run must be finalized as failed
    mock_finalize.assert_called_once()
    finalize_args = mock_finalize.call_args[0]
    assert finalize_args[2] == "failed", f"Expected 'failed', got {finalize_args[2]!r}"


def _make_collected_item_with_media(url_hash: str, media_url: str | None, media_type: str | None = "photo"):
    """Like _make_collected_item but with media_url/media_type set."""
    item = _make_collected_item(url_hash, f"t{url_hash}")
    item.media_url = media_url
    item.media_type = media_type if media_url else None
    return item


def test_pipeline_picks_rank1_media_when_available(mock_settings):
    """If rank-1 has media, hero source is rank-1's media."""
    mock_settings.enable_hero_media = True
    run_id = str(uuid4())
    digest_id = str(uuid4())

    items = [
        _make_collected_item_with_media("h0", "https://cdn.example.com/lead.jpg"),
        _make_collected_item_with_media("h1", "https://cdn.example.com/two.jpg"),
        _make_collected_item_with_media("h2", None),
    ]
    choices = [_make_choice(i + 1, f"h{i}") for i in range(3)]
    raw_rows = [_make_raw_row(f"h{i}") for i in range(3)]
    ranked_rows_flat = [{"rank": i + 1, "id": str(uuid4())} for i in range(3)]

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    captured: dict = {}

    async def fake_publish_with_hero(**kwargs):
        captured.update(kwargs)
        return 700, 701

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run"), \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=raw_rows), \
         patch("src.pipeline.record_ranked_items", return_value=ranked_rows_flat), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest", return_value=digest_id) as mock_create, \
         patch("src.pipeline.mark_digest_published") as mock_mark_pub, \
         patch("src.pipeline.mark_digest_failed"), \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=choices)), \
         patch("src.pipeline.summarize_item", new=AsyncMock(return_value="summary")), \
         patch("src.pipeline.translate_item", new=AsyncMock(return_value=_make_translated())), \
         patch("src.pipeline.publish_digest_with_hero", new=AsyncMock(side_effect=fake_publish_with_hero)), \
         patch("src.pipeline.format_digest", return_value=("digest text", "chash123")):

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=items)
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            asyncio.run(run_daily(mock_settings, dry_run=False))

    assert captured["hero_source"] == "https://cdn.example.com/lead.jpg"
    assert captured["hero_type"] == "photo"
    # create_pending_digest got the hero metadata
    create_kwargs = mock_create.call_args.kwargs
    assert create_kwargs["hero_media_url"] == "https://cdn.example.com/lead.jpg"
    assert create_kwargs["hero_media_type"] == "photo"
    # mark_digest_published got the hero message id
    pub_kwargs = mock_mark_pub.call_args.kwargs
    assert pub_kwargs["hero_message_id"] == 700


def test_pipeline_falls_back_to_default_when_no_item_has_media(mock_settings):
    """If no selected item carries media, the default banner is used."""
    mock_settings.enable_hero_media = True
    mock_settings.default_hero_path = "assets/default_hero.png"
    run_id = str(uuid4())
    digest_id = str(uuid4())

    items = [_make_collected_item_with_media(f"h{i}", None) for i in range(3)]
    choices = [_make_choice(i + 1, f"h{i}") for i in range(3)]
    raw_rows = [_make_raw_row(f"h{i}") for i in range(3)]
    ranked_rows_flat = [{"rank": i + 1, "id": str(uuid4())} for i in range(3)]

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    captured: dict = {}

    async def fake_publish_with_hero(**kwargs):
        captured.update(kwargs)
        return None, 801  # hero failed scenarios are independent — test default path

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run"), \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=raw_rows), \
         patch("src.pipeline.record_ranked_items", return_value=ranked_rows_flat), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest", return_value=digest_id), \
         patch("src.pipeline.mark_digest_published"), \
         patch("src.pipeline.mark_digest_failed"), \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=choices)), \
         patch("src.pipeline.summarize_item", new=AsyncMock(return_value="summary")), \
         patch("src.pipeline.translate_item", new=AsyncMock(return_value=_make_translated())), \
         patch("src.pipeline.publish_digest_with_hero", new=AsyncMock(side_effect=fake_publish_with_hero)), \
         patch("src.pipeline.format_digest", return_value=("digest text", "chash123")):

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=items)
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            asyncio.run(run_daily(mock_settings, dry_run=False))

    assert captured["hero_source"] == "assets/default_hero.png"
    assert captured["hero_type"] == "photo"


def test_publish_timeout_records_manual_check_message(mock_settings):
    """A possible-send timeout should leave an explicit manual-check failure."""
    run_id = str(uuid4())
    digest_id = str(uuid4())

    items = [_make_collected_item(f"h{i}", f"t{i}") for i in range(5)]
    choices = [_make_choice(i + 1, f"h{i}") for i in range(5)]
    raw_rows = [_make_raw_row(f"h{i}") for i in range(5)]
    ranked_rows_flat = [{"rank": i + 1, "id": str(uuid4())} for i in range(5)]

    existing = MagicMock()
    existing.url_hashes = set()
    existing.title_hashes = set()

    with patch("src.pipeline.get_client"), \
         patch("src.pipeline.get_ai_client"), \
         patch("src.pipeline.load_sources", return_value=_make_sources_mock()), \
         patch("src.pipeline.create_run", return_value=run_id), \
         patch("src.pipeline.finalize_run") as mock_finalize, \
         patch("src.pipeline.find_existing_hashes", return_value=existing), \
         patch("src.pipeline.insert_raw_items", return_value=raw_rows), \
         patch("src.pipeline.record_ranked_items", return_value=ranked_rows_flat), \
         patch("src.pipeline.record_processed_items"), \
         patch("src.pipeline.create_pending_digest", return_value=digest_id), \
         patch("src.pipeline.mark_digest_published"), \
         patch("src.pipeline.mark_digest_failed") as mock_mark_failed, \
         patch("src.pipeline.rank_items", new=AsyncMock(return_value=choices)), \
         patch("src.pipeline.summarize_item", new=AsyncMock(return_value="summary")), \
         patch("src.pipeline.translate_item", new=AsyncMock(return_value=_make_translated())), \
         patch("src.pipeline.publish_digest", new=AsyncMock(side_effect=TimeoutError("slow"))), \
         patch("src.pipeline.format_digest", return_value=("digest text", "chash123")):

        rss_mock = MagicMock()
        rss_mock.collect = AsyncMock(return_value=items)
        with patch("src.pipeline.RssCollector", return_value=rss_mock):
            with pytest.raises(RuntimeError, match="Manual channel check required"):
                asyncio.run(run_daily(mock_settings, dry_run=False))

    mock_mark_failed.assert_called_once()
    assert "Manual channel check required" in mock_mark_failed.call_args[0][2]
    finalize_kwargs = mock_finalize.call_args.kwargs
    assert finalize_kwargs["items_collected"] == 5
    assert finalize_kwargs["items_after_dedup"] == 5
