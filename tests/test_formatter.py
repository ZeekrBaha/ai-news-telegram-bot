import pytest
from datetime import date
from src.publisher.formatter import (
    CHANNEL_TAG,
    MAX_CAPTION_LENGTH,
    MAX_TELEGRAM_LENGTH,
    WHY_IT_MATTERS_TOP_N,
    format_digest,
    format_hero_caption,
    is_valid_url,
)


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


def test_format_digest_titles_are_not_linked():
    """Editorial style: titles render as bold, never as <a href>."""
    items = [make_item(url="https://example.com/article")]
    text, _ = format_digest(items)
    assert "href" not in text
    assert "<b>Заголовок статьи</b>" in text


def test_format_digest_renders_single_channel_tag_not_hashtag_wall():
    """The hashtag wall is replaced by a single brand tag at the bottom."""
    items = [
        make_item(hashtags=["#AI", "#LLM"], rank=1),
        make_item(hashtags=["#AI", "#GPT"], rank=2),
    ]
    text, _ = format_digest(items)
    # The brand tag appears exactly once, and per-item hashtags are gone.
    assert text.count(CHANNEL_TAG) == 1
    assert "#LLM" not in text
    assert "#GPT" not in text


def test_format_digest_why_it_matters_only_for_top_n():
    """`💡 почему важно` should only render for the top ranked items."""
    items = [
        make_item(rank=r, why_it_matters_ru=f"Важно для номера {r}.")
        for r in range(1, 6)
    ]
    text, _ = format_digest(items)
    # Top-N items get a why-line; lower-ranked items don't.
    for r in range(1, WHY_IT_MATTERS_TOP_N + 1):
        assert f"Важно для номера {r}." in text
    for r in range(WHY_IT_MATTERS_TOP_N + 1, 6):
        assert f"Важно для номера {r}." not in text


def test_format_digest_why_it_matters_omitted_when_empty():
    """Empty why_it_matters strings should not produce a stray bullet."""
    items = [make_item(rank=1, why_it_matters_ru="")]
    text, _ = format_digest(items)
    assert "💡" not in text


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


def test_format_hero_caption_basic():
    lead = {"title_ru": "OpenAI запускает новую модель", "url": "https://example.com/x"}
    caption = format_hero_caption(lead, channel_date=date(2026, 5, 14))
    assert "AI Дайджест 14.05.2026" in caption
    assert "OpenAI запускает новую модель" in caption
    # Caption no longer carries a source link.
    assert "href" not in caption
    assert len(caption) <= MAX_CAPTION_LENGTH


def test_format_hero_caption_escapes_html():
    lead = {"title_ru": '<script>alert(1)</script>', "url": "https://example.com/x"}
    caption = format_hero_caption(lead, channel_date=date(2026, 5, 14))
    assert "<script>" not in caption
    assert "&lt;script&gt;" in caption


def test_format_hero_caption_renders_title_in_bold():
    lead = {"title_ru": "Заголовок", "url": "javascript:alert(1)"}
    caption = format_hero_caption(lead, channel_date=date(2026, 5, 14))
    # No link wrapping under any condition.
    assert "javascript:" not in caption
    assert "href" not in caption
    assert "<b>Заголовок</b>" in caption


def test_format_hero_caption_trims_long_title():
    huge_title = "Очень длинный заголовок " * 100
    lead = {"title_ru": huge_title, "url": "https://example.com/x"}
    caption = format_hero_caption(lead, channel_date=date(2026, 5, 14))
    assert len(caption) <= MAX_CAPTION_LENGTH
    assert "…" in caption


def test_format_hero_caption_defaults_to_today():
    lead = {"title_ru": "Заголовок", "url": "https://example.com/x"}
    caption = format_hero_caption(lead)
    assert "AI Дайджест" in caption
    assert "Заголовок" in caption


def test_format_hero_caption_no_robot_emoji():
    """Robot emoji in the header was a giveaway tell — should be gone."""
    lead = {"title_ru": "Заголовок", "url": "https://example.com/x"}
    caption = format_hero_caption(lead)
    assert "🤖" not in caption
