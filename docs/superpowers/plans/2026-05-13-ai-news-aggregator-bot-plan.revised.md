# AI News Aggregator Bot - Implementation Plan

Date: 2026-05-13  
Spec: `docs/superpowers/specs/2026-05-13-ai-news-aggregator-bot-design.md`  
Status: Revised plan for fresh implementation sessions

## Phase 0 - Ground Rules and API Choices

This implementation should stay boring and explicit. The MVP is one Dockerized Python service with one daily scheduled job. The main risks are duplicate publishing, bad LLM JSON, Telegram formatting failures, and leaking secrets. Every phase below includes guards for those risks.

### Confirmed API choices

- Telethon reads channel messages through a file-backed user session.
- `python-telegram-bot` sends one message through the Bot API. No polling application is needed.
- OpenAI model is configurable through `OPENAI_MODEL`; default `gpt-4o-mini`.
- LLM outputs must be schema validated before use.
- Supabase is the only persistent store.
- APScheduler v3.x is the process scheduler.
- The scheduled sync job calls `asyncio.run(run_daily())`. Do not mix a blocking scheduler inside an already-running event loop.
- Use Telegram HTML parse mode for the MVP because it is easier to escape reliably than MarkdownV2.

### Forbidden anti-patterns

- Do not insert raw items and then dedupe by querying the same table without excluding current-run rows.
- Do not use `url text unique` as the only dedupe mechanism.
- Do not allow null `url_hash`.
- Do not publish before a pending digest row exists.
- Do not automatically retry Telegram publishing after an ambiguous timeout.
- Do not commit `.env`, session files, service-role keys, tokens, or generated local secrets.
- Do not trust LLM JSON without validation.

## Phase 1 - Project Skeleton and Configuration

### Implement

Create the repo skeleton:

```text
src/
  main.py
  config.py
  scheduler.py
  pipeline.py
  collectors/
  ai/
  publisher/
  database/
  scripts/
tests/
config/sources.yaml
.env.example
.gitignore
Dockerfile
docker-compose.yml
pyproject.toml
```

`src/config.py`:

- Define `Settings` with `pydantic-settings`.
- Load `.env`.
- Include `openai_model`, `digest_top_n`, `min_digest_items`, and `max_age_hours`.
- Validate timezone and numeric bounds.
- Load `config/sources.yaml` into typed source config models.

`.gitignore` must include:

```gitignore
.env
.env.*
sessions/
telethon_session/
*.session
*.session-journal
__pycache__/
.pytest_cache/
.ruff_cache/
```

### Dependencies

Pin broad compatible ranges:

```text
python-telegram-bot>=21.0
telethon>=1.36
feedparser>=6.0
httpx>=0.27
openai>=1.50
supabase>=2.5
apscheduler>=3.10,<4
pydantic>=2.7
pydantic-settings>=2.3
tenacity>=8.2
pyyaml>=6.0
pytest>=8
pytest-asyncio>=0.23
ruff>=0.5
```

### Verification

- `uv sync` resolves.
- `uv run python -m src.main --help` exits cleanly.
- Loading settings without required variables produces a clear validation error.
- `config/sources.yaml` parses into typed objects.

## Phase 2 - Database Schema and Repository

### Implement schema migration

Create `schema.sql` with tables:

- `runs`
- `raw_items`
- `ranked_items`
- `processed_items`
- `digests`

Critical constraints:

- `raw_items.url_hash text not null unique`
- `raw_items.title_hash text not null`
- `raw_items.run_id references runs(id)`
- `digests.run_id unique`
- `digests.status in ('pending', 'published', 'failed')`
- unique `(run_id, rank)` on `ranked_items`

Do not rely on `url text unique`, because null URLs and non-canonical URLs break dedupe.

### Implement repository functions

`src/database/repository.py`:

- `create_run() -> UUID`
- `finalize_run(run_id, status, counts, error=None)`
- `find_existing_hashes(url_hashes, title_hashes) -> ExistingHashes`
- `insert_raw_items(run_id, items) -> list[RawItemRow]`
- `record_ranked_items(run_id, ranked_items)`
- `record_processed_items(processed_items)`
- `create_pending_digest(run_id, channel_id, content_hash, item_ids) -> UUID`
- `mark_digest_published(digest_id, message_id)`
- `mark_digest_failed(digest_id, error)`

### Dedupe contract

Repository code should support pre-insert dedupe:

1. Caller provides candidate `CollectedItem` objects with hashes already computed.
2. `find_existing_hashes` queries previous rows by `url_hash` and `title_hash`.
3. Caller filters candidates.
4. `insert_raw_items` inserts only unseen candidates.

The unique `url_hash` constraint remains a final safety net for race conditions.

### Verification

- Unit test: new item is inserted once and skipped on second run.
- Unit test: same title with a different URL can be flagged as likely duplicate.
- Unit test: Telegram item with no URL still has a deterministic `url_hash`.
- Integration test against a test schema verifies a complete run row chain.

## Phase 3 - Collectors and Canonicalization

### Implement data model

`src/collectors/base.py`:

- `CollectedItem` dataclass.
- `Collector` protocol with `async def collect() -> list[CollectedItem]`.
- canonical URL helper.
- title normalization helper.
- `sha256_text`.

### RSS collector

`src/collectors/rss.py`:

- Fetch all feeds with `httpx.AsyncClient`.
- Use 10 second timeout per feed.
- Use `asyncio.gather(..., return_exceptions=True)` so one broken feed does not fail the batch.
- Parse entries with `feedparser`.
- Read entry fields with `.get(...)`, not direct attributes.
- Convert dates using `calendar.timegm`, not `time.mktime`.
- Strip HTML to plain text before storing content.
- Truncate content for LLM input.

### Telegram collector

`src/collectors/telegram.py`:

- Use `TelegramClient(session_name, api_id, api_hash)`.
- Iterate newest to oldest and break when messages are older than cutoff.
- Build source identity from channel and message id.
- For public channels, source URL is `https://t.me/{username}/{message_id}`.
- For private channels, use `https://t.me/c/{internal_id}/{message_id}` when possible.
- Do not assume `m.link` exists.
- Skip empty messages unless they include enough useful text.

### Telethon login helper

`src/scripts/telethon_login.py`:

- Interactive one-time script.
- Writes to `sessions/<TELETHON_SESSION_NAME>.session`.
- Prints logged-in account metadata, never the session content.

### Verification

- RSS dry-run prints collected count and first titles.
- Telegram dry-run prints collected count and first message titles/snippets.
- Unit tests cover date parsing, canonical URL generation, private/public Telegram URL generation, and no-URL hashing.

## Phase 4 - AI Client, Ranking, Summarization, Translation

### Implement

`src/ai/client.py`:

- Lazy OpenAI client.
- Uses `OPENAI_API_KEY`.
- Uses `OPENAI_MODEL`.
- Applies 30 second timeout.
- Tenacity retry wrapper for transient API errors.

`src/ai/ranker.py`:

- One LLM call for all candidates.
- Returns up to `DIGEST_TOP_N`.
- Validates response into a model like:

```python
class RankedChoice(BaseModel):
    id: str
    rank: int
    score: float
    reasoning: str

class RankingResponse(BaseModel):
    items: list[RankedChoice]
```

`src/ai/summarizer.py`:

- Per selected item.
- Generates concise English or neutral source-language summary for intermediate use.
- Validates non-empty output.

`src/ai/translator.py`:

- Per summarized item.
- Produces Russian output:
  - `title_ru`
  - `bullets_ru`, length 3-5
  - `why_it_matters_ru`
  - `hashtags`, max 5, each starts with `#`
- Validates with Pydantic.

### Prompt files

Store prompts under `src/ai/prompts/`:

- `ranker_system.txt`
- `summarizer_system.txt`
- `translator_system.txt`

Prompts should explicitly require JSON if JSON mode is used. If schema/structured output is available through the selected OpenAI SDK path, prefer it. Otherwise use JSON mode plus strict Pydantic validation and repair/fallback logic.

### Fallback behavior

If translator validation fails after retries:

- Drop that item if enough other items remain.
- Otherwise use a degraded fallback only if the spec owner accepts English fallback.
- Record `validation_notes` in `processed_items`.

### Verification

- Mock OpenAI tests cover valid JSON, invalid JSON, missing fields, wrong hashtag format, retry, and fallback.
- Ranking always returns unique ids and rank order.
- Translator cannot pass with fewer than 3 bullets or malformed hashtags.

## Phase 5 - Formatter and Telegram Publisher

### Formatter

`src/publisher/formatter.py`:

- Build one digest string.
- Use Telegram HTML parse mode.
- Escape all generated text with `html.escape`.
- Validate URLs before placing inside `<a href="...">`.
- Header format: short Russian digest title with date.
- For each item:
  - numbered title
  - 3-5 bullets
  - "Почему важно" sentence
  - source link
- Footer: deduped hashtags.

Length handling:

1. If over 4096 chars, shorten `why_it_matters_ru`.
2. If still over, shorten bullets.
3. If still over, remove lowest-ranked items until valid, but do not go below `MIN_DIGEST_ITEMS`.
4. If still over, fail the run before publishing.

### Publisher

`src/publisher/telegram_bot.py`:

- Use `telegram.Bot`.
- Use `telegram.constants.ParseMode.HTML`.
- Return `message.message_id`.
- Do not retry publish automatically from inside the publisher.

### Verification

- Formatter test checks output length, HTML escaping, link validation, hashtag dedupe, and item removal behavior.
- Manual test sends one digest to a private test channel before production channel use.

## Phase 6 - Pipeline Orchestration

### Implement

`src/pipeline.py::run_daily(dry_run=False)`:

1. `run_id = create_run()`
2. collect RSS and Telegram candidates
3. canonicalize and filter by age/content
4. `existing = find_existing_hashes(...)`
5. filter unseen candidates before insert
6. insert unseen raw items
7. if fewer than `MIN_DIGEST_ITEMS`, finalize `skipped`
8. rank top items
9. summarize and translate selected items
10. record ranked and processed rows
11. format digest
12. if `dry_run`, print digest and finalize success without publishing
13. create pending digest row with content hash
14. publish once
15. mark digest published
16. finalize run success

### Error handling

- Wrap the whole pipeline in a top-level try/except that finalizes the run.
- Store tracebacks in `runs.error`.
- Do not publish if ranking or formatting fails.
- If publish fails, mark pending digest failed and run failed.
- If publish timeout is ambiguous, mark it failed with a clear manual-check message.

### Verification

- Integration test: successful run creates raw, ranked, processed, digest, and success run rows.
- Failure injection: publisher raises, digest is failed, run is failed, no retry occurs.
- Dedupe test: second run with same source data is skipped or publishes only genuinely new items.
- Dry run never calls publisher.

## Phase 7 - Scheduler, CLI, Docker, Deployment

### CLI

`src/main.py` supports:

- `--once`
- `--dry-run`
- default scheduler mode

### Scheduler

`src/scheduler.py`:

- `BlockingScheduler(timezone=settings.timezone)`
- cron trigger from `SCHEDULE_HOUR` and `SCHEDULE_MINUTE`
- job body calls `asyncio.run(run_daily())`

### Docker

Use `python:3.12-slim`, mount:

- `.env`
- `config/`
- `sessions/`

Do not copy `.env` or sessions into the image.

### Deployment runbook

1. Create Supabase project.
2. Run `schema.sql`.
3. Create Telegram bot and add it as admin to the output channel.
4. Get Telegram `api_id` and `api_hash`.
5. Run Telethon login locally.
6. Copy session file to VPS `sessions/`.
7. Fill `.env` and `config/sources.yaml`.
8. Run `docker compose run --rm bot uv run python -m src.main --once --dry-run`.
9. Send one test digest to a private channel.
10. Point to production channel.
11. `docker compose up -d`.

### Verification

- Container starts.
- Dry run works inside container.
- Restart preserves Telethon session.
- First scheduled run creates a successful `runs` row.

## Phase 8 - Final Quality Gate

### Required checks

- `ruff check .`
- `pytest`
- dry-run against real RSS sources
- dry-run with Telegram collector if session is available
- one private-channel publish test
- grep audit for forbidden secrets and files

### Secret audit

Run checks that ensure no committed file contains:

- `OPENAI_API_KEY`
- `SUPABASE_SERVICE_KEY`
- `TELEGRAM_BOT_TOKEN`
- `.session`
- real `api_hash`

### Documentation match

Confirm implementation matches:

- pre-insert dedupe
- unique `url_hash`
- `MIN_DIGEST_ITEMS`
- pending digest before publish
- no automatic publish retry
- HTML parse mode
- explicit async boundary through `asyncio.run`
- schema-validated LLM output

## Execution Order

Run phases in order:

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7 -> Phase 8
```

Estimated MVP effort with AI assistance:

- Phase 1: 30 minutes
- Phase 2: 75 minutes
- Phase 3: 90 minutes
- Phase 4: 90 minutes
- Phase 5: 60 minutes
- Phase 6: 75 minutes
- Phase 7: 45 minutes
- Phase 8: 45 minutes

Total: about 8.5 hours for a working, testable MVP.

## User Inputs Needed Before Phase 3

- Telegram source channel usernames.
- Output Telegram channel id or username.
- Whether degraded English fallback is acceptable.
- Whether first production publish should go directly to the real channel or a private test channel first.
