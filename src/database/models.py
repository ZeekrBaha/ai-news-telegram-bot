from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RunRow:
    id: UUID
    started_at: datetime
    status: str
    items_collected: int = 0
    items_after_dedup: int = 0
    items_published: int = 0
    finished_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class RawItemRow:
    id: UUID
    run_id: UUID
    source_type: str
    source_name: str
    source_item_id: str
    url_hash: str
    title_hash: str
    title: str
    url: str | None = None
    canonical_url: str | None = None
    content: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class ExistingHashes:
    url_hashes: frozenset[str]
    title_hashes: frozenset[str]
