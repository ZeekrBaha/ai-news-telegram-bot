import json
import logging
from pathlib import Path
from pydantic import BaseModel, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

logger = logging.getLogger(__name__)


class TranslatedItem(BaseModel):
    title_ru: str
    bullets_ru: list[str]
    why_it_matters_ru: str = ""
    hashtags: list[str] = []

    @field_validator("bullets_ru")
    @classmethod
    def validate_bullets(cls, v: list[str]) -> list[str]:
        # 2-4 short sentences. Older prompt asked for 3-5; accept the wider 2-5
        # window so we don't fail on borderline outputs.
        if not (2 <= len(v) <= 5):
            raise ValueError(f"bullets_ru must have 2-5 items, got {len(v)}")
        return v

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, v: list[str]) -> list[str]:
        # Hashtags removed from the editorial output, but the field is preserved
        # for schema compatibility and bounded for safety if a future prompt
        # re-introduces them.
        if len(v) > 5:
            raise ValueError(f"hashtags must have at most 5 items, got {len(v)}")
        for tag in v:
            if not tag.startswith("#"):
                raise ValueError(f"hashtag must start with #: {tag}")
        return v

    @field_validator("title_ru")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title_ru cannot be empty")
        return v.strip()

    @field_validator("why_it_matters_ru")
    @classmethod
    def validate_why(cls, v: str) -> str:
        # Allowed to be empty: the prompt asks the model to omit "why it matters"
        # for routine product/research news.
        return v.strip()


def _load_system_prompt() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / "translator_system.txt").read_text(encoding="utf-8")


def _load_russian_summarizer_prompt() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / "summarizer_ru_system.txt").read_text(encoding="utf-8")


@retry(
    retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.25, min=0.25, max=4),
    reraise=True,
)
async def translate_item(
    client: AsyncOpenAI,
    model: str,
    title: str,
    summary_en: str,
    url: str | None = None,
) -> TranslatedItem:
    """Translate and adapt an item to Russian. Returns validated TranslatedItem."""
    system_prompt = _load_system_prompt()

    url_info = f"\nSource URL: {url}" if url else ""
    user_message = f"Title: {title}\n\nSummary: {summary_en}{url_info}"

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        return TranslatedItem(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse translation: {e}\nRaw: {raw}") from e


@retry(
    retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.25, min=0.25, max=4),
    reraise=True,
)
async def process_russian_item(
    client: AsyncOpenAI,
    model: str,
    title: str,
    content: str,
) -> TranslatedItem:
    """
    Build a TranslatedItem directly from Russian-language source content.

    Replaces the summarize→translate two-call chain with a single Russian-only
    call. Saves one OpenAI call per Russian item per run and preserves the
    original phrasing instead of running it through a Russian→English→Russian
    roundtrip.
    """
    system_prompt = _load_russian_summarizer_prompt()
    user_message = f"Заголовок: {title}\n\nТекст: {content}"

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        return TranslatedItem(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse Russian summary: {e}\nRaw: {raw}") from e
