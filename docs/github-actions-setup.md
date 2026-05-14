# Running the bot from GitHub Actions

This guide sets up daily publishing on GitHub Actions instead of your laptop.

## Why GitHub Actions

- **Free.** Public repos get unlimited minutes; private repos get 2,000/month. One run uses ~2 minutes/day = ~60 min/month.
- **Zero infrastructure.** No VPS to maintain.
- **Secure secrets.** Keys are encrypted at rest and injected as env vars at runtime, then destroyed with the runner.
- **Manual reruns.** One click in the Actions tab.

## Cron schedule

`.github/workflows/daily-digest.yml` runs at `0 6 * * *` UTC = **09:00 Europe/Moscow**. GitHub cron is best-effort: in practice it fires within 5–15 minutes of the scheduled time. For a daily news digest, this is fine.

Change the schedule by editing the `cron:` line in the workflow file. Cron syntax is `minute hour day month weekday`.

---

## One-time setup

### 1. Open the repo on GitHub

Navigate to `https://github.com/ZeekrBaha/ai-news-telegram-bot`.

### 2. Add Repository Secrets

In the repo, click:

**Settings** (top tab) → **Secrets and variables** (left sidebar) → **Actions** → **New repository secret**

Add each secret below — the **Name** must match exactly. Paste the value from your local `.env` file.

| Secret name | What goes in it |
| --- | --- |
| `OPENAI_API_KEY` | The `sk-proj-...` key from OpenAI |
| `TELEGRAM_BOT_TOKEN` | The `8458187153:AAGb...` token from BotFather |
| `TELEGRAM_CHANNEL_ID` | `@ainewsdigestme` (or numeric `-100...` for private channels) |
| `SUPABASE_URL` | `https://xxxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | The `sb_secret_...` or `eyJ...` service-role key |

**Optional — only if you read from Telegram channels (not just RSS):**

| Secret name | What goes in it |
| --- | --- |
| `TELEGRAM_API_ID` | Numeric ID from my.telegram.org |
| `TELEGRAM_API_HASH` | Hash from my.telegram.org |
| `TELETHON_SESSION_BASE64` | Base64-encoded Telethon session file (see step 3) |

If you skip these, the bot runs RSS-only — which is what you're doing today and is perfectly fine.

### 3. (Optional) Upload Telethon session file

If you want to read Telegram channels as a source, the bot needs a `sessions/*.session` file that holds your logged-in Telegram user. We base64-encode it into a GitHub secret.

On your laptop:

```bash
cd /Users/baha/Desktop/llm-ai-projects/ai-news-bot-spec
base64 -i sessions/reader.session | pbcopy   # macOS: copies to clipboard
# (Linux: base64 sessions/reader.session > /tmp/session.b64; cat /tmp/session.b64 | xclip)
```

Then in GitHub: Settings → Secrets and variables → Actions → New repository secret:

- **Name:** `TELETHON_SESSION_BASE64`
- **Value:** paste from clipboard

Note: this file is equivalent to your Telegram account. If it leaks, regenerate by running `uv run python -m src.scripts.telethon_login` locally and re-uploading.

### 4. (Optional) Add Repository Variables for tuning

These are **not** secrets — just configurable settings. Same UI, but the **Variables** tab next to Secrets.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-4o-mini` | Override to use a stronger model |
| `DIGEST_TOP_N` | `5` | Max items per digest |
| `MIN_DIGEST_ITEMS` | `3` | Skip if fewer new items |
| `MAX_AGE_HOURS` | `36` | Drop items older than this |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose runs |
| `ENABLE_HERO_MEDIA` | `true` | Set to `false` to publish text-only (kill switch) |

You don't need to set any of these — defaults are fine. The variable system is here for when you want to tune behavior without changing code.

### 5. Run the database migration in Supabase

The new hero-media columns need to exist before the workflow can record them.

1. Sign in at https://supabase.com → open your project.
2. Left sidebar → **SQL Editor** → **New query**.
3. Paste this and click **Run**:

```sql
alter table digests add column if not exists hero_message_id bigint;
alter table digests add column if not exists hero_media_url text;
alter table digests add column if not exists hero_media_type text;
```

This is safe to run multiple times.

### 6. Commit and push the workflow

Once the file is committed and pushed to `master`, GitHub picks it up automatically. No "activation" step needed.

---

## Running it

### Scheduled run

It fires daily at 09:00 Moscow. Nothing to do.

### Manual run (e.g. testing tonight)

1. Go to the repo on GitHub.
2. Click the **Actions** tab.
3. Pick **Daily Digest** from the left sidebar.
4. Click **Run workflow** (right side, dropdown button).
5. Choose:
   - `Use workflow from: master`
   - `Dry run`: leave unchecked to publish for real, check it to preview without sending
6. Click the green **Run workflow** button.

A new run appears within seconds. Click into it to watch live logs. Total runtime is ~2 minutes.

### What success looks like

- Run shows green ✅ in the Actions tab.
- A new message appears in `@ainewsdigestme` with hero photo + digest text.
- New row in Supabase `digests` table with `status='published'`.

### What failure looks like

- Run shows red ❌.
- Click into the run, expand the failed step to see the error.
- New row in Supabase `digests` table with `status='failed'` and an error message.

---

## Troubleshooting

**"OPENAI_API_KEY is required" error:** the secret name doesn't match. Check Settings → Secrets — the name must be exactly `OPENAI_API_KEY`, no typo.

**Run succeeds but nothing appears in the channel:** check the run's logs for "Marking run skipped" — that means dedup filtered everything (no new items since last run). Wait until tomorrow or temporarily lower `MAX_AGE_HOURS` via a Repository Variable.

**Telegram send fails:** the bot might've lost admin permission on the channel. Re-add it as admin with "Post Messages" permission.

**Cron not firing:** GitHub disables scheduled workflows in repos with 60+ days of no activity. Push any commit to reactivate, or just trigger manually.

---

## Switching back to laptop runs

Nothing changes — `uv run python -m src.main --once` still works locally. GitHub Actions doesn't lock the bot in any way. Both setups can coexist; just don't run them simultaneously (you'd get duplicate publishes).
