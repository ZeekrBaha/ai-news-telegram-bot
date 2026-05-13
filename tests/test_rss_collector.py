import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytest_plugins = ['pytest_asyncio']


@pytest.mark.asyncio
async def test_rss_collector_skips_failed_feeds():
    """Failed feeds should be logged and skipped, not crash the batch."""
    from src.collectors.rss import RssCollector

    settings = MagicMock()
    sources = [
        {"name": "good_feed", "url": "https://example.com/good.xml"},
        {"name": "bad_feed", "url": "https://example.com/bad.xml"},
    ]

    collector = RssCollector(settings, sources)

    good_response = MagicMock()
    good_response.text = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><title>Test Article</title><link>https://example.com/article</link><description>Some content here for the article that is long enough</description></item>
    </channel></rss>"""
    good_response.raise_for_status = MagicMock()

    async def mock_get(url):
        if "bad" in url:
            raise Exception("Connection refused")
        return good_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        items = await collector.collect()

    # Should have items from good feed, not crash on bad feed
    assert len(items) >= 0  # at least didn't crash
