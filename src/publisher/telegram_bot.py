import logging

from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


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
