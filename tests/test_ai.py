import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


def make_mock_response(content: str):
    """Create a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---- Ranker tests ----

@pytest.mark.asyncio
async def test_ranker_valid_response():
    from src.ai.ranker import rank_items
    from src.collectors.base import CollectedItem

    items = [
        CollectedItem(
            source_type="rss", source_name="blog", source_item_id="1",
            url="https://example.com/1", canonical_url="https://example.com/1",
            url_hash="aaa", title_hash="bbb", title="GPT-5 Released",
            content="OpenAI releases GPT-5 with major improvements.",
            published_at=datetime.now(timezone.utc), raw={}
        ),
    ]

    valid_response = json.dumps({
        "items": [{"id": "aaa", "rank": 1, "score": 0.95, "reasoning": "Major release"}]
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(valid_response))

    result = await rank_items(mock_client, "gpt-4o-mini", items, top_n=5)
    assert len(result) == 1
    assert result[0].rank == 1
    assert result[0].id == "aaa"


@pytest.mark.asyncio
async def test_ranker_invalid_json_raises():
    from src.ai.ranker import rank_items
    from src.collectors.base import CollectedItem

    items = [
        CollectedItem(
            source_type="rss", source_name="blog", source_item_id="1",
            url=None, canonical_url=None, url_hash="aaa", title_hash="bbb",
            title="Test", content="Content", published_at=datetime.now(timezone.utc), raw={}
        ),
    ]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response("not json"))

    with pytest.raises(ValueError, match="Failed to parse"):
        await rank_items(mock_client, "gpt-4o-mini", items, top_n=5)
    assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_ranker_unknown_id_retries_and_raises():
    from src.ai.ranker import rank_items
    from src.collectors.base import CollectedItem

    items = [
        CollectedItem(
            source_type="rss", source_name="blog", source_item_id="1",
            url=None, canonical_url=None, url_hash="known", title_hash="bbb",
            title="Test", content="Content", published_at=datetime.now(timezone.utc), raw={}
        ),
    ]

    invalid_response = json.dumps({
        "items": [{"id": "unknown", "rank": 1, "score": 0.9, "reasoning": "bad id"}]
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(invalid_response))

    with pytest.raises(ValueError, match="unknown ids"):
        await rank_items(mock_client, "gpt-4o-mini", items, top_n=5)
    assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_ranker_duplicate_ranks_retries_and_raises():
    from src.ai.ranker import rank_items
    from src.collectors.base import CollectedItem

    items = [
        CollectedItem(
            source_type="rss", source_name="blog", source_item_id="1",
            url=None, canonical_url=None, url_hash="a", title_hash="ta",
            title="A", content="Content", published_at=datetime.now(timezone.utc), raw={}
        ),
        CollectedItem(
            source_type="rss", source_name="blog", source_item_id="2",
            url=None, canonical_url=None, url_hash="b", title_hash="tb",
            title="B", content="Content", published_at=datetime.now(timezone.utc), raw={}
        ),
    ]

    invalid_response = json.dumps({
        "items": [
            {"id": "a", "rank": 1, "score": 0.9, "reasoning": "first"},
            {"id": "b", "rank": 1, "score": 0.8, "reasoning": "duplicate"},
        ]
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(invalid_response))

    with pytest.raises(ValueError, match="duplicate ranks"):
        await rank_items(mock_client, "gpt-4o-mini", items, top_n=5)
    assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_ranker_empty_items():
    from src.ai.ranker import rank_items

    mock_client = AsyncMock()
    result = await rank_items(mock_client, "gpt-4o-mini", [], top_n=5)
    assert result == []
    mock_client.chat.completions.create.assert_not_called()


# ---- Translator tests ----

@pytest.mark.asyncio
async def test_translator_valid():
    from src.ai.translator import translate_item, TranslatedItem

    valid = json.dumps({
        "title_ru": "ГПТ-5 вышел",
        "bullets_ru": ["Пункт 1", "Пункт 2", "Пункт 3"],
        "why_it_matters_ru": "Важно потому что...",
        "hashtags": ["#AI", "#OpenAI"]
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(valid))

    result = await translate_item(mock_client, "gpt-4o-mini", "GPT-5 released", "Summary here")
    assert isinstance(result, TranslatedItem)
    assert result.title_ru == "ГПТ-5 вышел"
    assert len(result.bullets_ru) == 3


@pytest.mark.asyncio
async def test_translator_too_few_bullets_fails():
    from src.ai.translator import translate_item

    invalid = json.dumps({
        "title_ru": "Title",
        "bullets_ru": ["Only one bullet"],
        "why_it_matters_ru": "Reason",
        "hashtags": ["#AI"]
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(invalid))

    with pytest.raises(ValueError):
        await translate_item(mock_client, "gpt-4o-mini", "Title", "Summary")


@pytest.mark.asyncio
async def test_translator_bad_hashtag_fails():
    from src.ai.translator import translate_item

    invalid = json.dumps({
        "title_ru": "Title",
        "bullets_ru": ["Bullet 1", "Bullet 2", "Bullet 3"],
        "why_it_matters_ru": "Reason",
        "hashtags": ["no_hash_prefix"]  # missing #
    })

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(invalid))

    with pytest.raises(ValueError):
        await translate_item(mock_client, "gpt-4o-mini", "Title", "Summary")


@pytest.mark.asyncio
async def test_translator_missing_fields_fails():
    from src.ai.translator import translate_item

    invalid = json.dumps({"title_ru": "Only title"})  # missing required fields

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=make_mock_response(invalid))

    with pytest.raises(ValueError):
        await translate_item(mock_client, "gpt-4o-mini", "Title", "Summary")


# ---- TranslatedItem validation unit tests (no mock) ----

def test_translated_item_valid():
    from src.ai.translator import TranslatedItem
    item = TranslatedItem(
        title_ru="Заголовок",
        bullets_ru=["п1", "п2", "п3"],
        why_it_matters_ru="Важно",
        hashtags=["#AI", "#LLM"]
    )
    assert item.title_ru == "Заголовок"


def test_translated_item_too_many_bullets():
    from src.ai.translator import TranslatedItem
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TranslatedItem(
            title_ru="T", bullets_ru=["1", "2", "3", "4", "5", "6"],
            why_it_matters_ru="W", hashtags=["#A"]
        )


def test_translated_item_too_many_hashtags():
    from src.ai.translator import TranslatedItem
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TranslatedItem(
            title_ru="T", bullets_ru=["1", "2", "3"],
            why_it_matters_ru="W",
            hashtags=["#1", "#2", "#3", "#4", "#5", "#6"]
        )
