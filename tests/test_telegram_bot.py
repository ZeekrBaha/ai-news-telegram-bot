from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.publisher.telegram_bot import publish_digest_with_hero

pytest_plugins = ["pytest_asyncio"]


def _mock_bot_returning(hero_id: int | None, digest_id: int):
    bot = MagicMock()
    if hero_id is None:
        bot.send_photo = AsyncMock(side_effect=Exception("hero failed"))
    else:
        bot.send_photo = AsyncMock(return_value=MagicMock(message_id=hero_id))
    bot.send_animation = AsyncMock(side_effect=Exception("not used"))
    bot.send_video = AsyncMock(side_effect=Exception("not used"))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=digest_id))
    return bot


@pytest.mark.asyncio
async def test_publish_digest_with_hero_happy_path():
    bot = _mock_bot_returning(hero_id=100, digest_id=101)
    with patch("src.publisher.telegram_bot.Bot", return_value=bot):
        hero_id, digest_id = await publish_digest_with_hero(
            bot_token="tok",
            channel_id="@chan",
            hero_source="https://example.com/img.jpg",
            hero_type="photo",
            hero_caption="caption",
            digest_text="<b>digest</b>",
        )
    assert hero_id == 100
    assert digest_id == 101
    bot.send_photo.assert_awaited_once()
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_falls_back_to_default_banner_when_primary_hero_fails():
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=[
        Exception("hotlink rejected"),
        MagicMock(message_id=200),  # default banner succeeds
    ])
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=201))

    with patch("src.publisher.telegram_bot.Bot", return_value=bot), \
         patch("src.publisher.telegram_bot._open_media", side_effect=lambda s: s):
        hero_id, digest_id = await publish_digest_with_hero(
            bot_token="tok",
            channel_id="@chan",
            hero_source="https://example.com/broken.jpg",
            hero_type="photo",
            hero_caption="caption",
            digest_text="<b>digest</b>",
            default_hero_path="assets/default_hero.png",
        )

    assert hero_id == 200
    assert digest_id == 201
    assert bot.send_photo.await_count == 2


@pytest.mark.asyncio
async def test_publish_text_only_when_both_heroes_fail():
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=Exception("everything fails"))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=300))

    with patch("src.publisher.telegram_bot.Bot", return_value=bot), \
         patch("src.publisher.telegram_bot._open_media", side_effect=lambda s: s):
        hero_id, digest_id = await publish_digest_with_hero(
            bot_token="tok",
            channel_id="@chan",
            hero_source="https://example.com/broken.jpg",
            hero_type="photo",
            hero_caption="caption",
            digest_text="<b>digest</b>",
            default_hero_path="assets/default_hero.png",
        )

    assert hero_id is None
    assert digest_id == 300
    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_does_not_retry_default_when_it_was_already_primary():
    """If the primary hero IS the default banner and it fails, we don't try twice."""
    bot = MagicMock()
    bot.send_photo = AsyncMock(side_effect=Exception("default banner missing"))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=400))

    with patch("src.publisher.telegram_bot.Bot", return_value=bot), \
         patch("src.publisher.telegram_bot._open_media", side_effect=lambda s: s):
        hero_id, digest_id = await publish_digest_with_hero(
            bot_token="tok",
            channel_id="@chan",
            hero_source="assets/default_hero.png",
            hero_type="photo",
            hero_caption="caption",
            digest_text="<b>digest</b>",
            default_hero_path="assets/default_hero.png",
        )

    assert hero_id is None
    assert digest_id == 400
    assert bot.send_photo.await_count == 1  # not retried
