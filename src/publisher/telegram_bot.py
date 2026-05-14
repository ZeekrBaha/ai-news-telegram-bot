import logging
from pathlib import Path
from typing import Literal

from telegram import Bot, InputFile
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

MediaType = Literal["photo", "animation", "video"]


async def publish_digest(
    bot_token: str,
    channel_id: str,
    text: str,
) -> int:
    """
    Publish digest to Telegram channel.

    Returns message_id on success.
    Does NOT retry internally — caller decides retry policy.
    """
    bot = Bot(token=bot_token)
    message = await bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return message.message_id


def _is_local_path(source: str) -> bool:
    """Heuristic: treat strings without a URL scheme as local file paths."""
    return not (source.startswith("http://") or source.startswith("https://"))


def _open_media(source: str):
    """Return an InputFile for local paths, or the raw URL string for remote sources."""
    if _is_local_path(source):
        path = Path(source)
        return InputFile(path.open("rb"), filename=path.name)
    return source


async def _send_hero(
    bot: Bot,
    channel_id: str,
    hero_source: str,
    hero_type: MediaType,
    caption: str,
) -> int:
    """Dispatch to the correct send_X method based on media type. Returns message_id."""
    media = _open_media(hero_source)

    if hero_type == "photo":
        msg = await bot.send_photo(
            chat_id=channel_id,
            photo=media,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    elif hero_type == "animation":
        msg = await bot.send_animation(
            chat_id=channel_id,
            animation=media,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    elif hero_type == "video":
        msg = await bot.send_video(
            chat_id=channel_id,
            video=media,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    else:
        raise ValueError(f"Unsupported hero media type: {hero_type}")

    return msg.message_id


async def publish_digest_with_hero(
    bot_token: str,
    channel_id: str,
    hero_source: str,
    hero_type: MediaType,
    hero_caption: str,
    digest_text: str,
    default_hero_path: str | None = None,
) -> tuple[int | None, int]:
    """
    Publish a digest as two consecutive messages: hero media (with caption), then full digest.

    If the hero send fails (Telegram rejects the URL, network error, etc.), we try the
    default hero PNG as a fallback. If that ALSO fails, we publish text-only and return
    (None, digest_message_id) so the run still ships.

    Returns (hero_message_id, digest_message_id). hero_message_id is None when both
    the requested hero and the default banner failed.

    Caller decides retry policy. The function never raises for hero failures; it only
    raises if the final text digest send fails.
    """
    bot = Bot(token=bot_token)
    hero_message_id: int | None = None

    try:
        hero_message_id = await _send_hero(bot, channel_id, hero_source, hero_type, hero_caption)
    except Exception as primary_error:
        logger.warning(
            "Hero send failed (source=%s, type=%s): %s",
            hero_source, hero_type, primary_error,
        )
        # Fall back to the bundled default banner if we weren't already trying it.
        if default_hero_path and default_hero_path != hero_source:
            try:
                hero_message_id = await _send_hero(
                    bot, channel_id, default_hero_path, "photo", hero_caption,
                )
                logger.info("Hero fell back to default banner")
            except Exception as fallback_error:
                logger.warning("Default banner also failed: %s", fallback_error)
                hero_message_id = None

    digest_message = await bot.send_message(
        chat_id=channel_id,
        text=digest_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    return hero_message_id, digest_message.message_id
