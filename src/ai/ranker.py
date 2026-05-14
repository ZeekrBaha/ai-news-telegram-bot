import json
import logging
from pathlib import Path
from pydantic import BaseModel, field_validator, model_validator
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

    @model_validator(mode="after")
    def validate_unique_choices(self) -> "RankingResponse":
        ids = [item.id for item in self.items]
        ranks = [item.rank for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("ranking response contains duplicate ids")
        if len(ranks) != len(set(ranks)):
            raise ValueError("ranking response contains duplicate ranks")
        return self


def _load_system_prompt() -> str:
    prompts_dir = Path(__file__).parent / "prompts"
    return (prompts_dir / "ranker_system.txt").read_text(encoding="utf-8")


@retry(
    retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.25, min=0.25, max=4),
    reraise=True,
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

    allowed_ids = {item.url_hash for item in items}
    unknown_ids = {choice.id for choice in ranking.items} - allowed_ids
    if unknown_ids:
        raise ValueError(f"Ranking response contains unknown ids: {sorted(unknown_ids)}")
    if len(ranking.items) > top_n:
        raise ValueError(f"Ranking response returned {len(ranking.items)} items, expected at most {top_n}")

    # Sort by rank and return top_n
    sorted_items = sorted(ranking.items, key=lambda x: x.rank)
    expected_ranks = list(range(1, len(sorted_items) + 1))
    actual_ranks = [item.rank for item in sorted_items]
    if actual_ranks != expected_ranks:
        raise ValueError(f"Ranking response ranks must be contiguous from 1: {actual_ranks}")

    return sorted_items
