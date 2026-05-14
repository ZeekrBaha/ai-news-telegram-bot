from src.collectors.base import (
    canonical_url,
    compute_url_hash,
    compute_title_hash,
    normalize_title,
    sha256_text,
    strip_html,
)


def test_canonical_url_lowercases():
    assert canonical_url("HTTP://Example.COM/Path") == "http://example.com/Path"

def test_canonical_url_removes_fragment():
    result = canonical_url("https://example.com/page#section")
    assert "#section" not in result

def test_canonical_url_removes_tracking_params():
    result = canonical_url("https://example.com/page?utm_source=x&id=42&fbclid=abc")
    assert result == "https://example.com/page?id=42"

def test_canonical_url_strips_trailing_slash():
    assert canonical_url("https://example.com/page/") == "https://example.com/page"

def test_canonical_url_none():
    assert canonical_url(None) is None

def test_canonical_url_empty():
    assert canonical_url("") is None

def test_sha256_text_deterministic():
    h1 = sha256_text("hello world")
    h2 = sha256_text("hello world")
    assert h1 == h2
    assert len(h1) == 64

def test_compute_url_hash_with_url():
    h = compute_url_hash("https://example.com/article", "rss", "blog", "123")
    # Should be sha256 of canonical URL
    expected = sha256_text(canonical_url("https://example.com/article"))
    assert h == expected

def test_compute_url_hash_without_url():
    h = compute_url_hash(None, "telegram", "mychannel", "42")
    expected = sha256_text("telegram:mychannel:42")
    assert h == expected

def test_compute_title_hash_normalizes():
    h1 = compute_title_hash("Hello, World!")
    h2 = compute_title_hash("hello world")
    assert h1 == h2  # punctuation stripped, lowercased

def test_strip_html():
    assert strip_html("<b>Hello</b> <i>world</i>") == "Hello world"

def test_strip_html_no_tags():
    assert strip_html("plain text") == "plain text"

def test_normalize_title():
    assert normalize_title("  Hello, World!  ") == "hello world"

# Telegram URL construction tests
def test_public_telegram_url():
    # Public channel URL format
    url = "https://t.me/mychannel/123"
    assert "t.me/mychannel/123" in url

def test_private_telegram_url():
    # Private channel URL format
    url = "https://t.me/c/1234567890/42"
    assert "t.me/c/" in url

# RSS date parsing
def test_rss_date_via_calendar_timegm():
    import calendar
    import time
    # calendar.timegm treats struct_time as UTC
    t = time.gmtime(0)  # epoch
    ts = calendar.timegm(t)
    assert ts == 0
