from src.collectors.base import extract_media_from_entry


def test_media_content_picks_photo():
    entry = {
        "media_content": [{"url": "https://example.com/hero.jpg", "type": "image/jpeg"}],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/hero.jpg"
    assert media_type == "photo"


def test_media_content_skips_thumbnails():
    entry = {
        "media_content": [
            {"url": "https://example.com/thumb-150x150.jpg", "type": "image/jpeg"},
            {"url": "https://example.com/hero.jpg", "type": "image/jpeg"},
        ],
    }
    url, _ = extract_media_from_entry(entry)
    assert url == "https://example.com/hero.jpg"


def test_media_thumbnail_fallback():
    entry = {
        "media_thumbnail": [{"url": "https://example.com/thumb.png"}],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/thumb.png"
    assert media_type == "photo"


def test_enclosure_picks_image():
    entry = {
        "enclosures": [{"href": "https://example.com/cover.png", "type": "image/png"}],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/cover.png"
    assert media_type == "photo"


def test_inline_img_from_summary():
    entry = {
        "summary": '<p>Story body <img src="https://example.com/inline.jpg" alt="x"/> trailing.</p>',
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/inline.jpg"
    assert media_type == "photo"


def test_inline_img_from_content():
    entry = {
        "content": [
            {"value": '<div><img src="https://example.com/body.png"/></div>'}
        ],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/body.png"
    assert media_type == "photo"


def test_returns_none_when_no_media():
    entry = {"summary": "no images here"}
    url, media_type = extract_media_from_entry(entry)
    assert url is None
    assert media_type is None


def test_priority_media_content_beats_thumbnail():
    entry = {
        "media_content": [{"url": "https://example.com/hero.jpg", "type": "image/jpeg"}],
        "media_thumbnail": [{"url": "https://example.com/tiny.png"}],
    }
    url, _ = extract_media_from_entry(entry)
    assert url == "https://example.com/hero.jpg"


def test_ignores_non_image_enclosure():
    entry = {
        "enclosures": [{"href": "https://example.com/podcast.mp3", "type": "audio/mpeg"}],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url is None
    assert media_type is None


def test_url_extension_classifies_when_mime_missing():
    entry = {
        "media_content": [{"url": "https://example.com/photo.png"}],
    }
    url, media_type = extract_media_from_entry(entry)
    assert url == "https://example.com/photo.png"
    assert media_type == "photo"
