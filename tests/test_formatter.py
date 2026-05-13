import pytest
from datetime import date
from src.publisher.formatter import format_digest, is_valid_url, MAX_TELEGRAM_LENGTH


def make_item(
    title_ru="Заголовок статьи",
    bullets_ru=None,
    why_it_matters_ru="Важно потому что это важно для индустрии.",
    hashtags=None,
    url="https://example.com/article",
    rank=1,
):
    return {
        "title_ru": title_ru,
        "bullets_ru": bullets_ru or ["Пункт 1", "Пункт 2", "Пункт 3"],
        "why_it_matters_ru": why_it_matters_ru,
        "hashtags": hashtags or ["#AI", "#LLM"],
        "url": url,
        "rank": rank,
    }


def test_format_digest_basic():
    items = [make_item()]
    text, hash_ = format_digest(items, channel_date=date(2026, 5, 13))
    assert "AI Дайджест" in text
    assert "13.05.2026" in text
    assert "Заголовок статьи" in text
    assert len(text) <= MAX_TELEGRAM_LENGTH
    assert len(hash_) == 64  # sha256 hex


def test_format_digest_escapes_html():
    items = [make_item(title_ru='<script>alert("xss")</script>')]
    text, _ = format_digest(items)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_format_digest_valid_url_becomes_link():
    items = [make_item(url="https://example.com/article")]
    text, _ = format_digest(items)
    assert 'href="https://example.com/article"' in text


def test_format_digest_invalid_url_no_link():
    items = [make_item(url="javascript:alert(1)")]
    text, _ = format_digest(items)
    assert "javascript:" not in text
    assert "href" not in text


def test_format_digest_no_url():
    items = [make_item(url=None)]
    text, _ = format_digest(items)
    assert "href" not in text


def test_format_digest_dedupes_hashtags():
    items = [
        make_item(hashtags=["#AI", "#LLM"], rank=1),
        make_item(hashtags=["#AI", "#GPT"], rank=2),  # #AI is duplicate
    ]
    text, _ = format_digest(items)
    # #AI should appear only once
    assert text.count("#AI") == 1 or text.count("#ai") == 1


def test_format_digest_too_long_removes_items():
    # Create 5 items with very long content that will exceed 4096 chars
    long_bullet = "А" * 300
    items = [
        make_item(
            title_ru=f"Статья {i}",
            bullets_ru=[long_bullet, long_bullet, long_bullet],
            why_it_matters_ru="А" * 200,
            rank=i,
        )
        for i in range(1, 6)
    ]
    # Should not raise, should trim items but keep min_items=3
    text, _ = format_digest(items, min_items=3)
    assert len(text) <= MAX_TELEGRAM_LENGTH


def test_format_digest_fails_if_still_too_long():
    # Single item with content so long it can't fit
    huge_title = "Я" * 5000
    items = [make_item(title_ru=huge_title)]
    with pytest.raises(ValueError, match="Refusing to publish"):
        format_digest(items, min_items=1)


def test_is_valid_url():
    assert is_valid_url("https://example.com") is True
    assert is_valid_url("http://example.com/path?q=1") is True
    assert is_valid_url("javascript:alert(1)") is False
    assert is_valid_url("ftp://example.com") is False
    assert is_valid_url(None) is False
    assert is_valid_url("") is False
