"""Unit tests for deduplication logic - pure functions, no DB."""
from src.database.models import ExistingHashes


def filter_new_items(candidates: list[dict], existing: ExistingHashes) -> list[dict]:
    """Return only candidates whose url_hash and title_hash are not in existing."""
    return [
        item
        for item in candidates
        if item["url_hash"] not in existing.url_hashes
        and item["title_hash"] not in existing.title_hashes
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _make_item(url_hash: str, title_hash: str) -> dict:
    return {"url_hash": url_hash, "title_hash": title_hash, "title": "Some title"}


def test_item_with_known_url_hash_is_filtered_out():
    existing = ExistingHashes(url_hashes=frozenset({"abc"}), title_hashes=frozenset())
    candidates = [_make_item("abc", "newtitle")]
    result = filter_new_items(candidates, existing)
    assert result == []


def test_item_with_known_title_hash_is_filtered_out():
    existing = ExistingHashes(url_hashes=frozenset(), title_hashes=frozenset({"xyz"}))
    candidates = [_make_item("newurl", "xyz")]
    result = filter_new_items(candidates, existing)
    assert result == []


def test_new_item_not_in_either_set_passes_through():
    existing = ExistingHashes(url_hashes=frozenset({"old_url"}), title_hashes=frozenset({"old_title"}))
    candidates = [_make_item("new_url", "new_title")]
    result = filter_new_items(candidates, existing)
    assert result == candidates


def test_multiple_items_only_unseen_ones_remain():
    existing = ExistingHashes(
        url_hashes=frozenset({"url1"}),
        title_hashes=frozenset({"title2"}),
    )
    item_pass = _make_item("url3", "title3")
    candidates = [
        _make_item("url1", "title1"),   # filtered: url_hash match
        _make_item("url2", "title2"),   # filtered: title_hash match
        item_pass,                       # passes through
    ]
    result = filter_new_items(candidates, existing)
    assert result == [item_pass]
