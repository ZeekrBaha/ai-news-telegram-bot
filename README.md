# AI News Telegram Bot

A daily Telegram channel that automatically collects the most important AI news from around the web, ranks the top stories with GPT, translates them into Russian, and publishes a single curated digest every morning.

**Live channel:** [@ainewsdigestme](https://t.me/ainewsdigestme)

---

## What it does

Every morning at 09:00 Europe/Moscow (configurable), the bot:

1. **Collects** fresh items from 9 RSS feeds (OpenAI, DeepMind, TechCrunch, Wired, The Verge, Ars Technica, MIT Tech Review, VentureBeat, Hacker News) and any configured Telegram channels.
2. **Deduplicates** against everything it has ever seen (by canonical URL hash + title hash).
3. **Filters** items older than 36 hours and those without enough content.
4. **Ranks** all candidates in a single OpenAI call and picks the top 5.
5. **Summarizes and translates** each selected story to Russian with a title, 3–5 bullets, a "почему важно" note, and hashtags.
6. **Formats** one Telegram HTML message under 4096 chars (auto-shrinks if needed).
7. **Publishes** once to the configured channel.
8. **Stores** every step in Supabase — raw items, ranking reasoning, generated text, and digest metadata — for a complete audit trail.

The whole flow runs as a single Dockerized Python service with APScheduler firing the daily job.

---

## Architecture

```
┌──────────────┐
│  APScheduler │  (daily cron 09:00 Moscow)
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│                    Pipeline orchestrator                │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐           │
│  │   RSS    │  │ Telegram │  │ Canonicalize │           │
│  │collector │  │collector │→ │   + hash     │           │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘           │
│       └──────┬──────┘                │                  │
│              ▼                       ▼                  │
│       ┌─────────────┐         ┌─────────────┐           │
│       │  Pre-insert │ ──────→ │  Supabase   │           │
│       │   dedupe    │         │  raw_items  │           │
│       └──────┬──────┘         └─────────────┘           │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │   Ranker    │ ──────→ │ Supabase    │           │
│       │ (OpenAI)    │         │ ranked_items│           │
│       └──────┬──────┘         └─────────────┘           │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │ Summarize + │ ──────→ │  Supabase   │           │
│       │ translate   │         │processed_items          │
│       │ (OpenAI)    │         └─────────────┘           │
│       └──────┬──────┘                                   │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │  Formatter  │ ──────→ │  Supabase   │           │
│       │   (HTML)    │         │   digests   │           │
│       └──────┬──────┘         │ (pending)   │           │
│              ▼                └─────────────┘           │
│       ┌─────────────┐                                   │
│       │  Telegram   │                                   │
│       │   Bot API   │ → @ainewsdigestme                 │
│       └─────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Pre-insert deduplication** — hashes are checked against the database *before* inserting new rows, so the current run never sees its own items as duplicates.
- **`url_hash text not null unique`** is the only authoritative dedup key. URL canonicalization (lowercase host, strip tracking params, normalize path) happens first.
- **Pending digest row** is written *before* the Telegram send, so a network timeout can never produce an unrecorded publish.
- **No automatic retry on publish** — if Telegram times out ambiguously, the run is marked failed and requires manual inspection.
- **Schema-validated LLM output** — every OpenAI response is parsed with Pydantic before it touches the rest of the pipeline.

---

## Tech stack

| Concern | Choice |
| --- | --- |
| Language | Python 3.12 |
| Package manager | `uv` |
| LLM | OpenAI (`gpt-4o-mini` by default, configurable) |
| Telegram read | Telethon (user session) |
| Telegram write | `python-telegram-bot` (Bot API) |
| RSS | `httpx` + `feedparser` |
| Database | Supabase (managed Postgres) |
| Scheduler | APScheduler v3 |
| Config | `pydantic-settings` + YAML |
| Retries | `tenacity` |
| Container | `python:3.12-slim` |

---

## Required API keys

You need accounts and tokens for three external services. None of them are committed to this repo — everything is read from `.env` at runtime.

### 1. OpenAI

- Get an API key at https://platform.openai.com/api-keys
- Set `OPENAI_API_KEY=sk-...`
- Default model is `gpt-4o-mini`. Change `OPENAI_MODEL` to use a different one.

### 2. Supabase

- Create a free project at https://supabase.com
- From the dashboard: **Project Settings → API Keys** → copy the **service role key** (starts with `sb_secret_` or `eyJ...`)
- From the dashboard home: copy the **Project URL** (looks like `https://xxxxx.supabase.co`)
- Open the **SQL Editor** and run the entire contents of `schema.sql` to create the 5 tables (`runs`, `raw_items`, `ranked_items`, `processed_items`, `digests`)
- Set `SUPABASE_URL=...` and `SUPABASE_SERVICE_KEY=...`

> **Important:** the service-role key is server-only. Never expose it to a client or commit it to git.

### 3. Telegram

**Bot (required for publishing):**
- Open Telegram, talk to [@BotFather](https://t.me/BotFather)
- Send `/newbot`, pick a name, pick a username ending in `bot`
- BotFather gives you a token like `8458187153:AAGb...` → set `TELEGRAM_BOT_TOKEN`
- Create a channel (public or private), add the bot as **admin** with "Post Messages" permission
- Set `TELEGRAM_CHANNEL_ID=@your_channel_username` (or the numeric `-100...` ID for private channels)

**User session (optional — only needed to read Telegram channels as a news source):**
- Go to https://my.telegram.org → log in with your phone → **API development tools**
- Create an app, copy `api_id` (number) and `api_hash` (string)
- Set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`
- Run `uv run python -m src.scripts.telethon_login` once to create a `sessions/*.session` file

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/ZeekrBaha/ai-news-telegram-bot.git
cd ai-news-telegram-bot
uv sync

# 2. Fill in secrets
cp .env.example .env
# edit .env with your real keys

# 3. Create database schema in Supabase SQL Editor
# (paste contents of schema.sql, click Run)

# 4. Configure RSS sources (optional — defaults are fine)
# edit config/sources.yaml

# 5. Dry run (no Telegram publish, just preview the digest)
uv run python -m src.main --once --dry-run

# 6. Real run (publishes to your channel once)
uv run python -m src.main --once

# 7. Production mode (runs every day at SCHEDULE_HOUR:SCHEDULE_MINUTE)
uv run python -m src.main
```

---

## `.env` reference

```env
# OpenAI
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini

# Telegram (Bot API — for publishing)
TELEGRAM_BOT_TOKEN=8458187153:AAGb...
TELEGRAM_CHANNEL_ID=@your_channel

# Telegram (User API — only if reading Telegram channels)
TELEGRAM_API_ID=0
TELEGRAM_API_HASH=placeholder
TELETHON_SESSION_NAME=reader

# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...

# Scheduling
SCHEDULE_HOUR=9
SCHEDULE_MINUTE=0
TIMEZONE=Europe/Moscow

# Tuning
DIGEST_TOP_N=5          # max items per digest
MIN_DIGEST_ITEMS=3      # skip run if fewer new items
MAX_AGE_HOURS=36        # drop items older than this
LOG_LEVEL=INFO
```

---

## Docker

```bash
docker compose up -d --build
```

`docker-compose.yml` mounts `./sessions` and `./config` at runtime and reads `./.env`. The image itself contains no secrets.

---

## Tests and quality gates

```bash
uv run ruff check .
uv run pytest
```

59 tests cover canonicalization, hash generation, dedupe, RSS parsing, AI client mocking, formatter escaping, length-reduction, and the full pipeline orchestrator with mocked OpenAI/Telegram.

---

## Project layout

```
ai-news-telegram-bot/
├── config/
│   └── sources.yaml          # RSS feeds + Telegram channels + filters
├── src/
│   ├── main.py               # CLI entry point (--once, --dry-run)
│   ├── config.py             # pydantic-settings loader
│   ├── scheduler.py          # APScheduler wrapper
│   ├── pipeline.py           # run_daily() orchestrator
│   ├── collectors/
│   │   ├── base.py           # CollectedItem, hashing, canonicalization
│   │   ├── rss.py            # httpx + feedparser
│   │   └── telegram.py       # Telethon iterator
│   ├── ai/
│   │   ├── client.py         # OpenAI async client + retry
│   │   ├── ranker.py         # rank candidates in one call
│   │   ├── summarizer.py     # per-item summary
│   │   ├── translator.py     # English → Russian + Pydantic validation
│   │   └── prompts/          # system prompts
│   ├── publisher/
│   │   ├── formatter.py      # HTML digest builder with length reduction
│   │   └── telegram_bot.py   # Bot API send_message wrapper
│   ├── database/
│   │   ├── client.py         # supabase-py wrapper
│   │   ├── models.py         # row dataclasses
│   │   └── repository.py     # create_run, insert_raw_items, etc.
│   └── scripts/
│       └── telethon_login.py # one-time interactive session creator
├── tests/                    # 59 unit + integration tests
├── schema.sql                # 5-table Postgres schema
├── Dockerfile
├── docker-compose.yml
├── .env.example              # template (no real keys)
└── pyproject.toml
```

---

## Failure handling

| Failure | Behavior |
| --- | --- |
| RSS feed times out | Warn, continue with other feeds |
| Telethon auth fails | Log error, continue RSS-only |
| OpenAI ranking fails after retries | Mark run failed, publish nothing |
| Translation fails for one item | Retry; if still invalid, drop the item |
| Fewer than `MIN_DIGEST_ITEMS` new items | Mark run skipped, publish nothing |
| Telegram publish definitively fails | Mark digest + run failed, no auto-retry |
| Telegram publish ambiguous timeout | Mark digest failed, require manual channel check |
| Unexpected exception | Caught at top level, traceback stored in `runs.error`, scheduler stays alive |

---

## Security checklist

The `.gitignore` already excludes:

- `.env`, `.env.*`
- `sessions/`, `*.session`, `*.session-journal`
- `telethon_session/`
- `.venv/`, `__pycache__/`, `dist/`, caches

Before pushing or sharing, double-check:

```bash
git status --short
git grep -nE "sk-proj-|sb_secret_|AAGbMX|api_hash"
```

The Telethon session file is **equivalent to your Telegram account** — store it with restrictive permissions (`chmod 600`) and never commit it.

---

## License

MIT
