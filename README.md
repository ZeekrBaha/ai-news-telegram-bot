# AI News Telegram Bot

A daily Telegram channel that automatically collects the most important AI news from around the web, ranks the top stories with GPT, translates them into Russian, and publishes a single curated digest every morning.

**Live channel:** [@ainewsdigestme](https://t.me/ainewsdigestme)

---

## What it does

Every morning at 09:00 Europe/Moscow, the bot:

1. **Collects** fresh items from 9 RSS feeds (OpenAI, DeepMind, TechCrunch, Wired, The Verge, Ars Technica, MIT Tech Review, VentureBeat, Hacker News) and any configured Telegram channels.
2. **Deduplicates** against everything it has ever seen (by canonical URL hash + title hash).
3. **Filters** items older than 36 hours and those without enough content.
4. **Ranks** all candidates in a single OpenAI call and picks the top 5.
5. **Picks a hero photo** from the rank-1 story's RSS-supplied image (with fallback through lower ranks and finally a bundled default banner).
6. **Summarizes and translates** each selected story to Russian with a title, 3–5 bullets, a "почему важно" note, and hashtags.
7. **Formats** one Telegram HTML digest under 4096 chars (auto-shrinks if needed).
8. **Publishes** as **two consecutive messages** to the channel: the hero photo with a short caption, then the full digest text.
9. **Stores** every step in Supabase — raw items, ranking reasoning, generated text, hero metadata, and digest message ids — for a complete audit trail.

Two deployment modes are supported:

- **GitHub Actions (recommended)** — a daily cron in `.github/workflows/daily-digest.yml`. Zero infrastructure, free for this workload, secrets encrypted at rest.
- **Self-hosted with APScheduler** — `docker compose up -d` on any always-on machine. Useful if you want precise schedule timing or you're already running a VPS.

---

## Architecture

```
┌──────────────────────────┐
│ GitHub Actions cron      │  (09:00 Europe/Moscow — primary)
│ or APScheduler in Docker │  (alternative for self-hosted)
└──────────────┬───────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│                    Pipeline orchestrator                │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐           │
│  │   RSS    │  │ Telegram │  │ Canonicalize │           │
│  │collector │  │collector │→ │  + hash      │           │
│  │ + media  │  │          │  │  + media URL │           │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘           │
│       └──────┬──────┘                │                  │
│              ▼                       ▼                  │
│       ┌─────────────┐         ┌─────────────┐           │
│       │  Pre-insert │ ──────→ │  Supabase   │           │
│       │   dedupe    │         │  raw_items  │           │
│       └──────┬──────┘         └─────────────┘           │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │   Ranker    │ ──────→ │  Supabase   │           │
│       │ (OpenAI)    │         │ ranked_items│           │
│       └──────┬──────┘         └─────────────┘           │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │ Summarize + │ ──────→ │   Supabase  │           │
│       │ translate   │         │processed_items          │
│       │ (OpenAI)    │         └─────────────┘           │
│       └──────┬──────┘                                   │
│              ▼                                          │
│       ┌─────────────┐                                   │
│       │  Hero pick  │  (rank-1 image → fallback ranks   │
│       │             │   → bundled default banner)       │
│       └──────┬──────┘                                   │
│              ▼                                          │
│       ┌─────────────┐         ┌─────────────┐           │
│       │  Formatter  │ ──────→ │  Supabase   │           │
│       │ (HTML+capt) │         │   digests   │           │
│       └──────┬──────┘         │ (pending)   │           │
│              ▼                └─────────────┘           │
│       ┌─────────────────┐                               │
│       │ Telegram Bot API│                               │
│       │ 1) sendPhoto    │ → @ainewsdigestme             │
│       │ 2) sendMessage  │                               │
│       └─────────────────┘                               │
└─────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Pre-insert deduplication** — hashes are checked against the database *before* inserting new rows, so the current run never sees its own items as duplicates.
- **`url_hash text not null unique`** is the only authoritative dedup key. URL canonicalization (lowercase host, strip tracking params, normalize path) happens first.
- **Pending digest row** is written *before* the Telegram send, so a network timeout can never produce an unrecorded publish.
- **No automatic retry on publish** — if Telegram times out ambiguously, the run is marked failed and requires manual inspection.
- **Schema-validated LLM output** — every OpenAI response is parsed with Pydantic before it touches the rest of the pipeline.
- **Two-message publish layout** — Telegram caps photo captions at 1024 chars; the full digest is ~3500. Sending hero + digest as two messages preserves all content without truncation.
- **Hero fallback chain** — broken hotlink falls back to the bundled `assets/default_hero.png`. If that also fails, the digest still publishes text-only — the hero is never a blocker for shipping.
- **Kill switch** — `ENABLE_HERO_MEDIA=false` reverts to text-only publishing without a code change.

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
| Scheduler | GitHub Actions cron (primary) or APScheduler v3 (self-hosted) |
| Default banner | Pillow (`PIL`), used by `src/scripts/generate_default_hero.py` |
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
# If upgrading from an older version, the file already includes safe
# `alter table ... add column if not exists` statements for the hero columns.

# 4. Configure RSS sources (optional — defaults are fine)
# edit config/sources.yaml

# 5. (optional) Regenerate the default hero banner with your own branding
uv run python -m src.scripts.generate_default_hero

# 6. Dry run (no Telegram publish, just preview the digest + hero pick)
uv run python -m src.main --once --dry-run

# 7. Real run (publishes hero + digest to your channel once)
uv run python -m src.main --once

# 8. Production mode (runs every day at SCHEDULE_HOUR:SCHEDULE_MINUTE)
#    Skip this step if you're deploying via GitHub Actions instead.
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

# Hero media (per-digest photo on top)
ENABLE_HERO_MEDIA=true                    # set false for instant text-only fallback
DEFAULT_HERO_PATH=assets/default_hero.png # used when no item has media
```

---

## Deployment options

### Option A — GitHub Actions (recommended)

A daily cron in `.github/workflows/daily-digest.yml` runs the pipeline on GitHub-hosted Ubuntu runners at 06:00 UTC = 09:00 Europe/Moscow. The workflow also exposes a manual **Run workflow** button in the Actions tab.

**Why this is the right default:**

- **Zero infrastructure.** No VPS to maintain, no `docker compose ps` to babysit.
- **Free for this workload.** ~2 minutes/day × ~30 runs/month = ~60 free minutes; GitHub gives 2,000/month on private repos and unlimited on public.
- **Encrypted secrets.** OpenAI / Telegram / Supabase keys live in encrypted Repository Secrets; they're injected as env vars at runtime, then destroyed with the runner.
- **One-click reruns.** Failed run? Click "Re-run all jobs" in the Actions tab.

**One-time setup:** see [`docs/github-actions-setup.md`](docs/github-actions-setup.md) for the full walkthrough — adding 5 Repository Secrets, running the schema migration in Supabase, and triggering the first manual run.

### Option B — Self-hosted (Docker)

```bash
docker compose up -d --build
```

`docker-compose.yml` mounts `./sessions` and `./config` at runtime and reads `./.env`. The image itself contains no secrets. APScheduler fires the daily job at exact schedule time.

Use this when you need precise scheduling (GitHub cron drifts 5–15 min), you're already running a VPS for other workloads, or you want the bot to read Telegram channels in real time without uploading a Telethon session as a base64 secret.

---

## Cost per run

Default config: `gpt-4o-mini`, top-5 digest, ~50 candidate items per day.

**Per-call breakdown:**

| Call | Count per run | Typical input tokens | Typical output tokens |
| --- | --- | --- | --- |
| Ranker (one batch call over all candidates) | 1 | ~10,000 | ~600 |
| Summarizer (one per selected story) | 5 | ~1,200 each | ~150 each |
| Translator (one per selected story) | 5 | ~400 each | ~300 each |

**Token totals per run:** ~18,000 input + ~2,850 output = ~21,000 tokens

**gpt-4o-mini pricing** (as of OpenAI's published rates):

- Input: $0.15 per 1M tokens
- Output: $0.60 per 1M tokens

**Math per run:**

- Input cost: 18,000 / 1,000,000 × $0.15 = **$0.0027**
- Output cost: 2,850 / 1,000,000 × $0.60 = **$0.0017**
- **Total per run: ~$0.0044 (less than half a cent)**

**Monthly (30 daily runs):** ~$0.13

**Annual:** ~$1.60

GitHub Actions and Supabase free tiers cover the rest. The whole bot runs on **roughly $2 per year**.

If you switch `OPENAI_MODEL` to `gpt-4o` (10× the cost), expect ~$0.04 per run → ~$1.30/month → ~$16/year. Still cheap, but you'd notice the difference.

---

## Tests and quality gates

```bash
uv run ruff check .
uv run pytest
```

87 tests cover canonicalization, hash generation, dedupe, RSS parsing, media extraction from each feed source type, AI client mocking, formatter escaping, length-reduction, hero caption building, the two-stage hero/digest publisher with three fallback paths, and the full pipeline orchestrator with mocked OpenAI/Telegram.

---

## Project layout

```
ai-news-telegram-bot/
├── .github/
│   └── workflows/
│       └── daily-digest.yml      # GitHub Actions cron + manual dispatch
├── assets/
│   └── default_hero.png          # bundled fallback banner for the hero photo
├── config/
│   └── sources.yaml              # RSS feeds + Telegram channels + filters
├── docs/
│   └── github-actions-setup.md   # secrets, migration, manual run walkthrough
├── src/
│   ├── main.py                   # CLI entry point (--once, --dry-run)
│   ├── config.py                 # pydantic-settings loader (incl. ENABLE_HERO_MEDIA)
│   ├── scheduler.py              # APScheduler wrapper (self-hosted mode)
│   ├── pipeline.py               # run_daily() orchestrator — hero pick lives here
│   ├── collectors/
│   │   ├── base.py               # CollectedItem (with media_url/type), extractor
│   │   ├── rss.py                # httpx + feedparser, populates media fields
│   │   └── telegram.py           # Telethon iterator
│   ├── ai/
│   │   ├── client.py             # OpenAI async client + retry
│   │   ├── ranker.py             # rank candidates in one call
│   │   ├── summarizer.py         # per-item summary
│   │   ├── translator.py         # English → Russian + Pydantic validation
│   │   └── prompts/              # system prompts
│   ├── publisher/
│   │   ├── formatter.py          # HTML digest + hero caption builder
│   │   └── telegram_bot.py       # sendPhoto + sendMessage with fallback
│   ├── database/
│   │   ├── client.py             # supabase-py wrapper
│   │   ├── models.py             # row dataclasses
│   │   └── repository.py         # create_run, insert_raw_items, etc.
│   └── scripts/
│       ├── telethon_login.py     # one-time interactive session creator
│       └── generate_default_hero.py  # regenerate the banner PNG via Pillow
├── tests/                        # 87 unit + integration tests
├── schema.sql                    # 5-table Postgres schema (incl. hero columns)
├── Dockerfile
├── docker-compose.yml
├── .env.example                  # template (no real keys)
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
| No item has a usable hero image | Use bundled `assets/default_hero.png` |
| Hero `sendPhoto` rejected (hotlink blocked, etc.) | Fall back to default banner |
| Default banner also fails | Skip hero, publish text-only digest, log warning |
| Telegram digest publish definitively fails | Mark digest + run failed, no auto-retry |
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
