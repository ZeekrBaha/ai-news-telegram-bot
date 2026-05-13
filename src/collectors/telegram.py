import logging
from datetime import datetime, timezone

from src.collectors.base import (
    CollectedItem,
    Collector,
    compute_title_hash,
    compute_url_hash,
    truncate_content,
)
from src.config import Settings

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 2000


class TelegramCollector(Collector):
    def __init__(self, settings: Settings, channels: list[str], max_age_hours: int = 36):
        self.settings = settings
        self.channels = channels
        self.max_age_hours = max_age_hours

    async def collect(self) -> list[CollectedItem]:
        try:
            from telethon import TelegramClient
            from telethon.tl.types import MessageMediaWebPage  # noqa: F401
        except ImportError:
            logger.error("telethon not installed")
            return []

        session_path = f"sessions/{self.settings.telethon_session_name}"
        client = TelegramClient(
            session_path,
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash,
        )

        items = []
        try:
            await client.start()
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)

            for channel in self.channels:
                try:
                    channel_items = await self._collect_channel(client, channel, cutoff)
                    items.extend(channel_items)
                except Exception as e:
                    logger.warning("Failed to collect from %s: %s", channel, e)
        finally:
            await client.disconnect()

        return items

    async def _collect_channel(
        self,
        client,
        channel: str,
        cutoff: datetime,
    ) -> list[CollectedItem]:
        entity = await client.get_entity(channel)
        items = []

        # Determine if private channel for URL construction
        is_private = not hasattr(entity, 'username') or not entity.username

        async for message in client.iter_messages(entity, limit=100):
            if message.date.replace(tzinfo=timezone.utc) < cutoff:
                break

            text = message.text or ""
            if len(text.strip()) < 50:
                continue

            title = text[:100].split('\n')[0].strip() or f"Message {message.id}"
            content = truncate_content(text)

            # Build source URL
            if is_private or not entity.username:
                # Use internal channel id format
                internal_id = entity.id
                source_url = f"https://t.me/c/{internal_id}/{message.id}"
            else:
                source_url = f"https://t.me/{entity.username}/{message.id}"

            source_item_id = str(message.id)
            channel_name = entity.username or str(entity.id)

            url_hash = compute_url_hash(source_url, "telegram", channel_name, source_item_id)
            title_hash = compute_title_hash(title)

            items.append(CollectedItem(
                source_type="telegram",
                source_name=channel_name,
                source_item_id=source_item_id,
                url=source_url,
                canonical_url=source_url,
                url_hash=url_hash,
                title_hash=title_hash,
                title=title,
                content=content,
                published_at=message.date.replace(tzinfo=timezone.utc),
                raw={"message_id": message.id, "channel": channel},
            ))

        return items
