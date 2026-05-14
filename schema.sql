-- AI News Bot Database Schema
-- All tables use uuid primary keys and created_at timestamps

create table runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text not null check (status in ('running', 'success', 'skipped', 'failed')),
  error text,
  items_collected int default 0,
  items_after_dedup int default 0,
  items_published int default 0
);

create table raw_items (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  run_id uuid references runs(id),
  source_type text not null,
  source_name text not null,
  source_item_id text not null,
  url text,
  canonical_url text,
  url_hash text not null unique,
  title_hash text not null,
  title text not null,
  content text,
  published_at timestamptz,
  raw jsonb,
  collected_at timestamptz default now()
);

create index raw_items_title_hash_idx on raw_items(title_hash);
create index raw_items_collected_at_idx on raw_items(collected_at);
create index raw_items_source_idx on raw_items(source_type, source_name, source_item_id);

create table ranked_items (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  raw_item_id uuid references raw_items(id),
  run_id uuid references runs(id),
  rank int not null,
  score float,
  reasoning text,
  unique (run_id, raw_item_id),
  unique (run_id, rank)
);

create table processed_items (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  ranked_item_id uuid references ranked_items(id) unique,
  summary_en text,
  title_ru text not null,
  bullets_ru text[] not null,
  why_it_matters_ru text,
  hashtags text[],
  validation_notes text
);

create table digests (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  run_id uuid references runs(id) unique,
  status text not null check (status in ('pending', 'published', 'failed')),
  content_hash text not null,
  telegram_message_id bigint,
  channel_id text not null,
  posted_at timestamptz,
  item_ids uuid[] not null,
  error text
);
