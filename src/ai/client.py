import logging
from openai import AsyncOpenAI
from src.config import Settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_ai_client(settings: Settings) -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=30.0,
        )
    return _client
