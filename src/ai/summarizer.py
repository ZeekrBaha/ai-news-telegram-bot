import logging
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from src.collectors.base import CollectedItem

logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / "summarizer_system.txt").read_text(encoding="utf-8")


@retry(
    retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def summarize_item(
    client: AsyncOpenAI,
    model: str,
    item: CollectedItem,
) -> str:
    """Summarize a single item. Returns English summary text."""
    system_prompt = _load_system_prompt()
    user_message = f"Title: {item.title}\n\nContent: {item.content}"

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
    )

    summary = response.choices[0].message.content.strip()
    if not summary:
        raise ValueError(f"Empty summary returned for item: {item.title}")

    return summary
