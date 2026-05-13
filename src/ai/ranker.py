import json
import logging
from pathlib import Path
from pydantic import BaseModel, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from src.collectors.base import CollectedItem

logger = logging.getLogger(__name__)


class RankedChoice(BaseModel):
    id: str
    rank: int
    score: float
    reasoning: str

    @field_validator("rank")
    @classmethod
    def rank_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("rank must be >= 1")
        return v

    @field_validator("score")
    @classmethod
    def score_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("score must be 0.0-1.0")
        return v


class RankingResponse(BaseModel):
    items: list[RankedChoice]

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("ranking response must contain items")
        return v


def _load_system_prompt() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / "ranker_system.txt").read_text(encoding="utf-8")


@retry(
    retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
async def rank_items(
    client: AsyncOpenAI,
    model: str,
    items: list[CollectedItem],
    top_n: int,
) -> list[RankedChoice]:
    """Rank items with one LLM call, return top_n ranked choices."""
    if not items:
        return []

    # Build input for the LLM
    items_input = [
        {
            "id": item.url_hash,  # use url_hash as stable id
            "title": item.title,
            "content": item.content[:500],  # brief snippet for ranking
            "source": item.source_name,
        }
        for item in items
    ]

    system_prompt = _load_system_prompt()
    user_message = (
        f"Rank the following {len(items)} news items. Return the top {top_n} most important ones.\n\n"
        f"Items:\n{json.dumps(items_input, ensure_ascii=False, indent=2)}"
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    raw = response.choices[0].message.content
    try:
        data = json.loads(raw)
        ranking = RankingResponse(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse ranking response: {e}\nRaw: {raw}") from e

    # Sort by rank and return top_n
    sorted_items = sorted(ranking.items, key=lambda x: x.rank)
    return sorted_items[:top_n]
