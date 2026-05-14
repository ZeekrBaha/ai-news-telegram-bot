# Hero Media in Daily Digest — Plan

**Goal:** Every digest post on `@ainewsdigestme` opens with one piece of visual media (image, gif, or video) sitting on top of the existing 5-story HTML text.

**Status:** Draft, awaiting your sign-off before I touch code.

---

## 1. Where the picture comes from

We already have the data — RSS feeds carry images in three standard places, and `feedparser` already exposes all of them in the `entry` dict we store in `raw_items.raw`. We just don't read them yet.

Source order, picked per-item, first match wins:

1. **`entry.media_content[0].url`** — the most reliable; this is what TechCrunch, Wired, The Verge, Ars Technica, MIT Tech Review use.
2. **`entry.media_thumbnail[0].url`** — fallback for some feeds.
3. **`entry.enclosures[0].href`** — used by VentureBeat and a few others; only if the `type` starts with `image/`, `video/`, or `image/gif`.
4. **`<img>` tag inside `entry.summary` / `entry.content`** — last-resort regex parse for feeds that inline images (OpenAI blog, DeepMind).
5. **Open Graph `og:image` from the article page** — only if all of the above fail and a URL exists. We make one extra GET, parse `<meta property="og:image">`, give up after 3 seconds.

If nothing is found, we fall back to a **static channel banner** (a single PNG you provide once, stored at `assets/default_hero.png`) so every post still has visual continuity.

**Why this order:** the first four are zero-cost (already in the parsed feed). Step 5 costs one HTTP request per item that needs it — capped at 5 candidates per run, so worst case adds ~5 short requests on top of today's pipeline.

---

## 2. What media types Telegram allows on top of a post

Telegram's Bot API has three "send X with caption" methods that fit our shape:

| Method | Accepts | Caption limit |
| --- | --- | --- |
| `sendPhoto` | JPEG / PNG / WebP | 1024 chars |
| `sendAnimation` | GIF / MP4 silent loop | 1024 chars |
| `sendVideo` | MP4 with audio | 1024 chars |
| `sendMessage` (today) | none | 4096 chars |

**The 1024-char caption is the hard constraint.** Today's 5-story digest is ~3500 chars. So if we want media + the full digest in one post, we have two viable patterns:

**Option A — Media + caption (single post, truncated digest)**
Send one `sendPhoto`/`sendAnimation`/`sendVideo` with a shortened digest (5 titles + URLs, no bullets, no "почему важно", no hashtags) as the caption. Loses most of the editorial value.

**Option B — Media post, then text post (two messages)** ← **recommended**
First message: `sendPhoto` with a short caption — just the digest header (`🤖 AI Дайджест 14.05.2026`) and maybe the lead story's title. Second message: today's full HTML digest, sent as `sendMessage` exactly like now. Both appear back-to-back in the channel and read as one unit. No content is lost.

**Option C — Single sendMessage with linked photo preview**
Keep one `sendMessage`, set `disable_web_page_preview=False`, and rely on Telegram to render the lead story's link preview at the top. Cheapest change, but the preview is small, depends on the article's own OG tags, and Telegram sometimes refuses to render it.

**Recommendation: Option B.** It's predictable, keeps the full text, and is the standard pattern for Telegram news channels.

---

## 3. Architecture changes

```
RSS / Telegram collector
        │
        ▼
CollectedItem  ← add `media_url: str | None`, `media_type: Literal["photo","animation","video"] | None`
        │
        ▼  (rank / summarize / translate stay the same)
        │
        ▼
Pipeline: pick lead story (rank 1), use its media as the hero
        │
        ▼
Publisher: publish_digest_with_media(hero_url, hero_type, caption, digest_text)
        │  1. sendPhoto / sendAnimation / sendVideo  (hero + short caption)
        │  2. sendMessage                            (full digest)
        ▼
@ainewsdigestme
```

**Hero selection rule:** the rank-1 item's media is the hero. If rank-1 has no media, fall through to rank-2, rank-3, etc. If none of the 5 selected items has media, use the static channel banner.

**Why not pick the "best" image:** ranking is already an LLM call; adding image-quality scoring would be another LLM call per item. Rank-1 is by definition the lead story, so its image is the editorially correct choice.

---

## 4. Files to change

| File | Change |
| --- | --- |
| `src/collectors/base.py` | Add `media_url`, `media_type` fields to `CollectedItem`. Add helper `extract_media_from_entry(entry) -> tuple[url, type] \| (None, None)`. |
| `src/collectors/rss.py` | Call the new helper, populate the two new fields. |
| `src/collectors/telegram.py` | Same — Telegram messages already carry photo/video metadata. |
| `src/publisher/telegram_bot.py` | Add `publish_digest_with_hero(...)`. Old `publish_digest` becomes a thin wrapper used by tests. |
| `src/publisher/formatter.py` | Add `format_hero_caption(items, date)` — a short caption under 1024 chars: header + lead title. |
| `src/pipeline.py` | Pick hero from ranked items, call new publisher signature. |
| `src/config.py` | Add `default_hero_path: str = "assets/default_hero.png"`, `enable_hero_media: bool = True` (kill switch). |
| `schema.sql` + `src/database/repository.py` | Add `digests.hero_message_id bigint`, `digests.hero_media_url text`, `digests.hero_media_type text`. We log both message ids on success. |
| `assets/default_hero.png` | New file — you provide this one PNG. |
| `tests/` | Add unit tests for media extraction + integration test with mocked Telegram. |

---

## 5. Detailed task list

### Task 1 — Media extraction (collectors)

Files:
- `src/collectors/base.py` — add `media_url`, `media_type` to `CollectedItem`; add `extract_media_from_entry()` helper that walks the 5 sources in order
- `src/collectors/rss.py` — wire it up
- `tests/test_media_extraction.py` — unit tests with fixture feeds for each source type

Test fixtures live in `tests/fixtures/feeds/` — I'll capture one real entry from each of the 9 RSS feeds so tests pin actual structure, not hypothetical.

### Task 2 — Default hero asset

You provide one image at `assets/default_hero.png` (a banner — recommend 1280×720 PNG, under 1 MB). Add it to `.gitignore`? No — commit it; it's not a secret. Update `.dockerignore` if needed.

### Task 3 — Hero caption formatter

File: `src/publisher/formatter.py` — add `format_hero_caption(date, lead_item) -> str`. Output:

```
<b>🤖 AI Дайджест 14.05.2026</b>

<a href="...">Главная история: {translated title of rank-1}</a>
```

Hard cap 1024 chars. Length-reduce by trimming the lead title if needed.

### Task 4 — Publisher

File: `src/publisher/telegram_bot.py` — new function:

```python
async def publish_digest_with_hero(
    bot_token: str,
    channel_id: str,
    hero_url: str,         # local path or remote URL
    hero_type: Literal["photo", "animation", "video"],
    hero_caption: str,
    digest_text: str,
) -> tuple[int, int]:      # (hero_message_id, digest_message_id)
```

Implementation:
1. If `hero_url` is a local path → open file, send as `InputFile`.
2. If `hero_url` is remote → pass URL string directly (Telegram fetches it). Fall back to downloading via httpx then re-uploading if Telegram returns "wrong file identifier" — some news sites block hotlinking.
3. Pick API method by `hero_type`: `send_photo` / `send_animation` / `send_video`.
4. After hero send succeeds, call `send_message` for the digest exactly like today.
5. Return both message ids.

Retry / failure: if hero send fails (any reason), log a warning and fall back to today's text-only `send_message`. We never block the daily digest on a media problem.

### Task 5 — Pipeline wiring

File: `src/pipeline.py`

After the ranking + translation steps, before publish:

```python
# Pick hero
hero = None
for choice, item in sorted(selected_items, key=lambda x: x[0].rank):
    if item.media_url:
        hero = (item.media_url, item.media_type)
        break
if hero is None:
    hero = (settings.default_hero_path, "photo")
```

Then build the hero caption from the rank-1 item's translated title, and call `publish_digest_with_hero` instead of `publish_digest`.

Pending-digest row writes both `hero_media_url` and `hero_media_type` *before* the send, same pattern as today.

### Task 6 — Schema migration

Append to `schema.sql`:

```sql
alter table digests add column if not exists hero_message_id bigint;
alter table digests add column if not exists hero_media_url text;
alter table digests add column if not exists hero_media_type text;
```

Migration is additive — no risk to existing rows. You'll paste this into Supabase SQL Editor once.

### Task 7 — Config + kill switch

`src/config.py`: add `enable_hero_media: bool = True` and `default_hero_path: str = "assets/default_hero.png"`. If `enable_hero_media=False`, pipeline uses today's text-only publish — instant rollback.

### Task 8 — Tests

- Unit: 6 cases in `test_media_extraction.py` (each source type + fallback chain + None).
- Unit: `test_format_hero_caption.py` — length cap, escaping.
- Integration: extend `test_pipeline.py` with one test where ranked items carry media and one where they don't (fallback hits default hero).
- Manual smoke: `uv run python -m src.main --once --dry-run` prints `[HERO] url=... type=photo` so we can eyeball it before going live.

### Task 9 — README

Document the kill switch + how to swap the default banner. Two short paragraphs.

---

## 6. Risks and trade-offs

| Risk | Mitigation |
| --- | --- |
| Telegram rejects a hotlinked URL | Re-upload via httpx download. If that fails, fall back to default banner. |
| Some feeds give tiny thumbnails (200×200) that look bad blown up | Skip images whose URL hints at `thumb`/`small`/`-150x` patterns. Cheap heuristic, no extra request. |
| og:image fetch slows the run | Hard 3-second timeout per item, only fired when steps 1–4 failed for that item. With 5 items, worst case 15s — well under our daily budget. |
| Two-post pattern looks busy in channel | Test with one live publish, you eyeball it, we revert if it looks worse. The kill switch is one env var. |
| Image rights / hotlinking ethics | We only use what the publisher's own RSS feed provided — that's an implicit grant for syndication. Default banner for the rest. |

---

## 7. Order of execution

1. **You approve this plan.** ← we are here
2. **You drop `assets/default_hero.png` in the project** (or I generate a placeholder).
3. **Task 1** — media extraction + fixture tests.
4. **Task 6** — run schema migration in Supabase.
5. **Tasks 3, 4, 5, 7** — formatter, publisher, pipeline, config (one commit each).
6. **Task 8** — tests pass.
7. **Dry run** — `--dry-run` prints hero plan, no publish.
8. **One live run** — publish to `@ainewsdigestme`, you eyeball it.
9. **Task 9** — README update.

Total work: ~half a day of focused coding once approved.

---

## 8. Decisions I need from you before coding

1. **Option B confirmed?** (hero post + text post, the recommended layout)
2. **Default hero image** — you provide one, or want me to generate a placeholder banner?
3. **Should we ever skip the post entirely if no media is found?** My recommendation: no, always publish; default banner handles it.
4. **Video / gif support on day one, or photos only first?** My recommendation: photos only first (covers ~95% of RSS items), add gif/video in a follow-up if you want.
