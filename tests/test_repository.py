"""Unit tests for repository functions - all DB calls are mocked."""
from unittest.mock import MagicMock
from uuid import UUID

from src.database.models import ExistingHashes
from src.database.repository import (
    create_pending_digest,
    find_existing_hashes,
    insert_raw_items,
    mark_digest_failed,
    mark_digest_published,
)


def make_mock_client():
    """Return a MagicMock that supports the Supabase chained query builder."""
    client = MagicMock()
    # Each call to .table() returns the same mock chain so we can track calls
    chain = MagicMock()
    client.table.return_value = chain
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    return client, chain


# ---------------------------------------------------------------------------
# find_existing_hashes
# ---------------------------------------------------------------------------


def test_find_existing_hashes_empty_input_returns_empty_frozensets():
    client, _ = make_mock_client()
    result = find_existing_hashes(client, [], [])
    assert result == ExistingHashes(url_hashes=frozenset(), title_hashes=frozenset())
    # No DB call should have been made
    client.table.assert_not_called()


def test_find_existing_hashes_calls_in_correctly():
    client = MagicMock()

    # We need two separate chains since the function calls .table() twice
    url_chain = MagicMock()
    url_chain.select.return_value = url_chain
    url_chain.in_.return_value = url_chain
    url_chain.execute.return_value = MagicMock(data=[{"url_hash": "abc"}])

    title_chain = MagicMock()
    title_chain.select.return_value = title_chain
    title_chain.in_.return_value = title_chain
    title_chain.execute.return_value = MagicMock(data=[{"title_hash": "xyz"}])

    client.table.side_effect = [url_chain, title_chain]

    result = find_existing_hashes(client, ["abc", "def"], ["xyz", "uvw"])

    # Verify url_hash query
    url_chain.select.assert_called_once_with("url_hash")
    url_chain.in_.assert_called_once_with("url_hash", ["abc", "def"])

    # Verify title_hash query
    title_chain.select.assert_called_once_with("title_hash")
    title_chain.in_.assert_called_once_with("title_hash", ["xyz", "uvw"])

    assert result.url_hashes == frozenset({"abc"})
    assert result.title_hashes == frozenset({"xyz"})


# ---------------------------------------------------------------------------
# insert_raw_items
# ---------------------------------------------------------------------------


def test_insert_raw_items_empty_list_returns_empty_no_db_call():
    client, _ = make_mock_client()
    result = insert_raw_items(client, UUID("00000000-0000-0000-0000-000000000001"), [])
    assert result == []
    client.table.assert_not_called()


# ---------------------------------------------------------------------------
# create_pending_digest
# ---------------------------------------------------------------------------


def test_create_pending_digest_returns_uuid_from_response():
    client, chain = make_mock_client()
    digest_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    chain.execute.return_value = MagicMock(data=[{"id": digest_id}])

    run_id = UUID("11111111-1111-1111-1111-111111111111")
    item_ids = [UUID("22222222-2222-2222-2222-222222222222")]

    result = create_pending_digest(client, run_id, "#channel", "hash123", item_ids)

    assert result == UUID(digest_id)
    client.table.assert_called_once_with("digests")
    chain.insert.assert_called_once_with(
        {
            "run_id": str(run_id),
            "status": "pending",
            "content_hash": "hash123",
            "channel_id": "#channel",
            "item_ids": [str(iid) for iid in item_ids],
        }
    )


# ---------------------------------------------------------------------------
# mark_digest_published
# ---------------------------------------------------------------------------


def test_mark_digest_published_calls_update_with_correct_status_and_message_id():
    client, chain = make_mock_client()
    digest_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    mark_digest_published(client, digest_id, message_id=42)

    client.table.assert_called_once_with("digests")
    update_call_kwargs = chain.update.call_args[0][0]
    assert update_call_kwargs["status"] == "published"
    assert update_call_kwargs["telegram_message_id"] == 42
    assert "posted_at" in update_call_kwargs
    chain.eq.assert_called_once_with("id", str(digest_id))


# ---------------------------------------------------------------------------
# mark_digest_failed
# ---------------------------------------------------------------------------


def test_mark_digest_failed_calls_update_with_failed_status():
    client, chain = make_mock_client()
    digest_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    mark_digest_failed(client, digest_id, error="something went wrong")

    client.table.assert_called_once_with("digests")
    update_call_kwargs = chain.update.call_args[0][0]
    assert update_call_kwargs["status"] == "failed"
    assert update_call_kwargs["error"] == "something went wrong"
    chain.eq.assert_called_once_with("id", str(digest_id))
